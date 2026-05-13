"""
Fetch historical OHLCV candles for a specific date.
Priority: local parquet cache (data/ohlcv/) → Upstox API fallback.
Used by the simulate/backfill endpoint to replay real trading days.
"""
import httpx
import pandas as pd
import structlog
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

UPSTOX_HISTORICAL_URL = "https://api.upstox.com/v2/historical-candle"

# Local parquet cache written by scripts/download_ohlcv.py
_PARQUET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ohlcv"

# Parquet DataFrames are cached in memory after first load (one per symbol)
_parquet_cache: dict[str, pd.DataFrame] = {}

# Upstox instrument keys for index symbols
INSTRUMENT_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}


def _load_parquet(symbol: str) -> pd.DataFrame | None:
    """Load and cache the full parquet file for a symbol."""
    if symbol in _parquet_cache:
        return _parquet_cache[symbol]
    path = _PARQUET_DIR / f"{symbol}_5min.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    _parquet_cache[symbol] = df
    return df


def _from_parquet(symbol: str, trading_date: date) -> pd.DataFrame:
    """Extract one day's 5-min candles from the local parquet cache."""
    df = _load_parquet(symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    ts_ist = df["timestamp"].dt.tz_convert("Asia/Kolkata")
    mask = ts_ist.dt.date == trading_date
    day = df[mask].copy().reset_index(drop=True)
    if day.empty:
        return pd.DataFrame()
    # Rename to standard columns expected by the rest of the app
    day = day.rename(columns={"timestamp": "timestamp"})
    return day[["timestamp", "open", "high", "low", "close", "volume"]]


async def fetch_historical_candles(symbol: str, trading_date: date) -> pd.DataFrame:
    """
    Fetch 5-minute candles for a symbol on a given trading date.
    Checks local parquet cache first (data/ohlcv/), falls back to Upstox API.
    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    Returns empty DataFrame if fetch fails or no data.
    """
    # Try local parquet first — zero latency, no rate limits
    if trading_date != date.today():
        cached = _from_parquet(symbol.upper(), trading_date)
        if not cached.empty:
            logger.debug("Historical candles from parquet cache", symbol=symbol, date=str(trading_date), candles=len(cached))
            return cached

    instrument_key = INSTRUMENT_KEYS.get(symbol.upper())
    if not instrument_key:
        logger.error("Unknown symbol for historical fetch", symbol=symbol)
        return pd.DataFrame()

    date_str = trading_date.strftime("%Y-%m-%d")
    encoded_key = quote(instrument_key, safe="")

    # Upstox uses a different endpoint for today vs historical dates
    # Interval: 1minute (5minute not supported) — we resample to 5m ourselves
    today = date.today()
    if trading_date == today:
        url = f"{UPSTOX_HISTORICAL_URL}/intraday/{encoded_key}/1minute"
    else:
        url = f"{UPSTOX_HISTORICAL_URL}/{encoded_key}/1minute/{date_str}/{date_str}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.upstox_access_token}",
                    "Api-Version": "2.0",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        candles_raw = data.get("data", {}).get("candles", [])
        if not candles_raw:
            logger.warning("No historical candles returned", symbol=symbol, date=date_str)
            return pd.DataFrame()

        # Upstox format: [timestamp, open, high, low, close, volume, oi]
        rows = []
        for c in candles_raw:
            rows.append({
                "timestamp": pd.to_datetime(c[0]),
                "open":      float(c[1]),
                "high":      float(c[2]),
                "low":       float(c[3]),
                "close":     float(c[4]),
                "volume":    float(c[5]),
            })

        df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

        # Resample 1-minute candles → 5-minute OHLCV
        df = df.set_index("timestamp")
        df5 = df.resample("5min").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna().reset_index()

        logger.info("Historical candles fetched", symbol=symbol, date=date_str, candles_5m=len(df5))
        return df5

    except Exception as e:
        logger.error("Failed to fetch historical candles", symbol=symbol, date=date_str, error=str(e))
        return pd.DataFrame()
