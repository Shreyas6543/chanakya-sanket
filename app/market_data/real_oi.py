"""
Real historical OI loader from NSE F&O Bhavcopy data.
Used by the backtest/backfill to replace fake circular OI with actual EOD OI snapshots.

Data directory: data/nse_oi/YYYY-MM-DD.csv
Columns: date, symbol, expiry, option_type, strike, oi, spot
"""

import pandas as pd
from pathlib import Path
from datetime import date
from functools import lru_cache

OI_DATA_DIR = Path("data/nse_oi")

# Cache loaded files to avoid re-reading disk on repeated calls
_cache: dict[str, pd.DataFrame] = {}


def _load_day(d: date) -> pd.DataFrame | None:
    key = d.isoformat()
    if key not in _cache:
        path = OI_DATA_DIR / f"{key}.csv"
        if not path.exists():
            _cache[key] = None
        else:
            _cache[key] = pd.read_csv(path)
    return _cache[key]


def get_real_oi_data(symbol: str, d: date) -> dict | None:
    """
    Returns OI data dict matching the format expected by OIBuildupStrategy:
        {
            "call_oi":      int,  # today's CE OI at ATM ±10% strikes (nearest expiry)
            "put_oi":       int,  # today's PE OI
            "prev_call_oi": int,  # yesterday's CE OI (same filter)
            "prev_put_oi":  int,  # yesterday's PE OI
        }

    Day-over-day OI change is a real signal: rising call OI = new long calls added = bullish.
    Uses EOD snapshots from NSE Bhavcopy data.
    Returns None if data not found for both today and previous day.
    """
    from datetime import timedelta

    # Find the two most recent available trading days on or before d
    available = []
    for days_back in range(10):
        target = date.fromordinal(d.toordinal() - days_back)
        df = _load_day(target)
        if df is not None and not df.empty:
            sym_df = df[df["symbol"] == symbol.upper()]
            if not sym_df.empty:
                available.append(sym_df)
                if len(available) == 2:
                    break

    if len(available) < 2:
        return None

    today_oi   = _sum_atm_oi(available[0])
    prev_oi    = _sum_atm_oi(available[1])

    if today_oi is None or prev_oi is None:
        return None

    return {
        "call_oi":      today_oi["ce_oi"],
        "put_oi":       today_oi["pe_oi"],
        "prev_call_oi": prev_oi["ce_oi"],
        "prev_put_oi":  prev_oi["pe_oi"],
    }


def _sum_atm_oi(df: pd.DataFrame) -> dict | None:
    """Sum CE and PE OI within ±10% of spot for the nearest expiry."""
    spot = float(df["spot"].iloc[0])

    df = df.copy()
    df["expiry"] = pd.to_datetime(df["expiry"])
    nearest_expiry = df["expiry"].min()
    near_df = df[
        (df["expiry"] == nearest_expiry) &
        (df["strike"] >= spot * 0.90) &
        (df["strike"] <= spot * 1.10)
    ]

    if near_df.empty:
        return None

    return {
        "ce_oi": int(near_df[near_df["option_type"] == "CE"]["oi"].sum()),
        "pe_oi": int(near_df[near_df["option_type"] == "PE"]["oi"].sum()),
    }


def oi_data_available() -> bool:
    """Returns True if the data/nse_oi directory exists and has files."""
    return OI_DATA_DIR.exists() and any(OI_DATA_DIR.glob("*.csv"))


def oi_coverage_stats() -> dict:
    """Return stats on how many days of OI data we have."""
    files = sorted(OI_DATA_DIR.glob("*.csv"))
    if not files:
        return {"count": 0}
    return {
        "count": len(files),
        "first": files[0].stem,
        "last":  files[-1].stem,
    }
