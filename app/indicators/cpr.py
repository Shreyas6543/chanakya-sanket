"""
Central Pivot Range (CPR) indicator.
Calculated from previous day's OHLC. Used for regime detection.

Formula (Zerodha Varsity):
  Pivot (P) = (High + Low + Close) / 3
  BC = (High + Low) / 2
  TC = 2 * P - BC

CPR width as % of price:
  Narrow (<0.15% of spot) = prior day indecisive → expect sideways
  Wide   (>0.15% of spot) = prior day trending   → expect trending

Reference: https://zerodha.com/varsity/chapter/the-central-pivot-range/
"""
import pandas as pd
from dataclasses import dataclass


@dataclass
class CPRResult:
    pivot: float
    bc: float
    tc: float
    width_pct: float   # abs(TC - BC) / pivot × 100
    is_narrow: bool    # True = expect sideways, False = expect trending


_NARROW_THRESHOLD_PCT = 0.15  # < 0.15% of pivot = narrow CPR


def calculate_cpr(candles: pd.DataFrame) -> CPRResult | None:
    """
    Calculate CPR from previous trading day's candles.
    Requires a candle buffer that spans at least 2 trading sessions.
    Returns None if insufficient data.
    """
    if len(candles) < 20:
        return None

    # Identify previous day's candles using the timestamp column
    if "timestamp" not in candles.columns:
        return None

    ts = pd.to_datetime(candles["timestamp"])
    dates = ts.dt.date.unique()

    if len(dates) < 2:
        return None

    # Use the second-to-last unique date as "previous day"
    prev_date = sorted(dates)[-2]
    prev_candles = candles[ts.dt.date == prev_date]

    if prev_candles.empty:
        return None

    prev_high  = float(prev_candles["high"].max())
    prev_low   = float(prev_candles["low"].min())
    prev_close = float(prev_candles["close"].iloc[-1])

    pivot = (prev_high + prev_low + prev_close) / 3
    bc    = (prev_high + prev_low) / 2
    tc    = 2 * pivot - bc

    # Width is absolute value (TC can be below BC on bearish days)
    width_pct = abs(tc - bc) / pivot * 100 if pivot > 0 else 0

    return CPRResult(
        pivot=round(pivot, 2),
        bc=round(bc, 2),
        tc=round(tc, 2),
        width_pct=round(width_pct, 4),
        is_narrow=width_pct < _NARROW_THRESHOLD_PCT,
    )
