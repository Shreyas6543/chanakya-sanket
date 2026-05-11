"""
Fetch historical OHLCV candles from Upstox for a specific date.
Used by the simulate endpoint to replay a real trading day.
"""
import httpx
import pandas as pd
import structlog
from datetime import date, datetime
from urllib.parse import quote

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

UPSTOX_HISTORICAL_URL = "https://api.upstox.com/v2/historical-candle"

# Upstox instrument keys for index symbols
INSTRUMENT_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}


async def fetch_historical_candles(symbol: str, trading_date: date) -> pd.DataFrame:
    """
    Fetch 5-minute candles for a symbol on a given trading date from Upstox.
    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    Returns empty DataFrame if fetch fails or no data.
    """
    instrument_key = INSTRUMENT_KEYS.get(symbol.upper())
    if not instrument_key:
        logger.error("Unknown symbol for historical fetch", symbol=symbol)
        return pd.DataFrame()

    date_str = trading_date.strftime("%Y-%m-%d")
    encoded_key = quote(instrument_key, safe="")
    url = f"{UPSTOX_HISTORICAL_URL}/{encoded_key}/5minute/{date_str}/{date_str}"

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
        logger.info("Historical candles fetched", symbol=symbol, date=date_str, count=len(df))
        return df

    except Exception as e:
        logger.error("Failed to fetch historical candles", symbol=symbol, date=date_str, error=str(e))
        return pd.DataFrame()
