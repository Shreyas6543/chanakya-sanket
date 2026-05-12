"""
Download 5-minute OHLCV candles for NIFTY and BANKNIFTY.

Data availability reality:
  - yfinance    : 5-min data limited to last 60 days only (Yahoo restriction)
  - Upstox API  : 5-min data up to ~2 years back (free, our primary source)
  - Paid sources: TrueData / Global Data Feed for 5yr history (₹3-8k/month)

This script uses Upstox historical API — gives ~2 years of 5-min candles.
That yields ~500 trading days × 2 symbols → enough for ML training.

Usage:
    python scripts/download_ohlcv.py                          # max lookback → today
    python scripts/download_ohlcv.py --start 2023-01-01
    python scripts/download_ohlcv.py --symbols NIFTY

Output:
    data/ohlcv/NIFTY_5min.parquet
    data/ohlcv/BANKNIFTY_5min.parquet
    Columns: timestamp, open, high, low, close, volume, symbol
"""

import argparse
import time
import os
import requests
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("data/ohlcv")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Upstox instrument keys for NSE indices
UPSTOX_INSTRUMENTS = {
    "NIFTY":     "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}

# yfinance tickers for NSE indices
YFINANCE_TICKERS = {
    "NIFTY":     "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}


# ── Upstox historical API ──────────────────────────────────────────────────────

def _upstox_token() -> str | None:
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    return token or None


def fetch_upstox_chunk(symbol: str, from_date: date, to_date: date, token: str) -> pd.DataFrame | None:
    """
    Upstox v2 historical candle API.
    Supports: 1minute, 30minute, day, week, month (NOT 5minute).
    We fetch 1-minute candles and resample to 5-minute.
    Max date range per call: ~1 month for 1-min data.
    """
    instrument = UPSTOX_INSTRUMENTS[symbol]
    url = (
        f"https://api.upstox.com/v2/historical-candle"
        f"/{requests.utils.quote(instrument, safe='')}"
        f"/1minute/{to_date.isoformat()}/{from_date.isoformat()}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"    Upstox {resp.status_code}: {resp.text[:200]}")
            return None
        candles = resp.json().get("data", {}).get("candles", [])
        if not candles:
            return None
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")

        # Resample 1-min → 5-min (market open aligned to 9:15 IST)
        df = df.set_index("timestamp")
        df5 = df.resample("5min", closed="left", label="left").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna(subset=["open"])
        df5 = df5.reset_index()
        df5["symbol"] = symbol
        return df5
    except Exception as e:
        print(f"    Upstox error: {e}")
        return None


def fetch_upstox(symbol: str, start: date, end: date, token: str) -> pd.DataFrame:
    """Fetch Upstox 1-min data in monthly chunks, resample to 5-min."""
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        # Monthly chunks — safe for 1-min data
        if chunk_start.month == 12:
            chunk_end = min(date(chunk_start.year + 1, 1, 1) - timedelta(days=1), end)
        else:
            chunk_end = min(date(chunk_start.year, chunk_start.month + 1, 1) - timedelta(days=1), end)
        print(f"    chunk: {chunk_start} → {chunk_end}", end="  ")
        df = fetch_upstox_chunk(symbol, chunk_start, chunk_end, token)
        if df is not None and not df.empty:
            print(f"{len(df)} bars")
            chunks.append(df)
        else:
            print("no data")
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.3)
    return pd.concat(chunks).drop_duplicates("timestamp") if chunks else pd.DataFrame()


# ── yfinance fallback ──────────────────────────────────────────────────────────

def fetch_yfinance(symbol: str, start: date, end: date) -> pd.DataFrame:
    """
    yfinance 5-min data. Max per call: 60 days.
    Fetches in 55-day chunks to stay within limit.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("    yfinance not installed. Run: pip install yfinance")
        return pd.DataFrame()

    ticker = YFINANCE_TICKERS[symbol]
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=55), end)
        print(f"    yfinance chunk: {chunk_start} → {chunk_end}")
        try:
            df = yf.download(
                ticker,
                start=chunk_start.isoformat(),
                end=(chunk_end + timedelta(days=1)).isoformat(),
                interval="5m",
                progress=False,
                auto_adjust=True,
            )
            if not df.empty:
                df = df.reset_index()
                # yfinance returns 'Datetime' column for intraday
                ts_col = "Datetime" if "Datetime" in df.columns else "Date"
                df = df.rename(columns={
                    ts_col:   "timestamp",
                    "Open":   "open",
                    "High":   "high",
                    "Low":    "low",
                    "Close":  "close",
                    "Volume": "volume",
                })
                # Handle MultiIndex columns from yfinance
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df = df[["timestamp", "open", "high", "low", "close", "volume"]]
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df["symbol"] = symbol
                chunks.append(df)
        except Exception as e:
            print(f"    yfinance error: {e}")
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(1)

    return pd.concat(chunks).drop_duplicates("timestamp") if chunks else pd.DataFrame()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download 5-min OHLCV for NIFTY + BANKNIFTY")
    # Upstox max lookback is ~2 years
    default_start = (date.today() - timedelta(days=730)).isoformat()
    parser.add_argument("--start",   default=default_start,            help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     default=date.today().isoformat(), help="End date YYYY-MM-DD")
    parser.add_argument("--symbols", default="NIFTY,BANKNIFTY",        help="Comma-separated symbols")
    args = parser.parse_args()

    start   = date.fromisoformat(args.start)
    end     = date.fromisoformat(args.end)
    symbols = [s.strip() for s in args.symbols.split(",")]
    token   = _upstox_token()

    if not token:
        print("ERROR: UPSTOX_ACCESS_TOKEN not set in .env")
        print("yfinance 5-min data is limited to last 60 days — not useful for ML.")
        print("Set your Upstox token and re-run.")
        return

    # Clamp start to Upstox max lookback (~2 years)
    max_lookback = date.today() - timedelta(days=730)
    if start < max_lookback:
        print(f"Note: Upstox 5-min history limited to ~2 years. Clamping start to {max_lookback}.")
        start = max_lookback

    print(f"Upstox token found.")
    print(f"Date range: {start} → {end}")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    for symbol in symbols:
        out_path = OUTPUT_DIR / f"{symbol}_5min.parquet"
        existing = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame()

        if not existing.empty:
            # Only fetch new data since last timestamp
            last_date = pd.to_datetime(existing["timestamp"]).max().date()
            if last_date >= end:
                print(f"[{symbol}] Already up to date ({last_date}). Skipping.")
                continue
            fetch_start = last_date + timedelta(days=1)
            print(f"[{symbol}] Incremental fetch: {fetch_start} → {end}")
        else:
            fetch_start = start
            print(f"[{symbol}] Full fetch: {fetch_start} → {end}")

        up_df = fetch_upstox(symbol, fetch_start, end, token)

        if up_df.empty:
            print(f"[{symbol}] No data returned from Upstox.\n")
            continue

        print(f"  → {len(up_df):,} candles from Upstox")

        combined = (
            pd.concat([existing, up_df]) if not existing.empty else up_df
        ).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

        combined.to_parquet(out_path, index=False)
        span = f"{combined['timestamp'].min()} → {combined['timestamp'].max()}"
        print(f"[{symbol}] Saved {len(combined):,} total candles → {out_path}")
        print(f"  span: {span}\n")


if __name__ == "__main__":
    main()
