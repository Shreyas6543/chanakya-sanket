import pandas as pd
from app.config import get_settings

settings = get_settings()


def detect_regime(candles: pd.DataFrame, atr_period: int = 14, ma_period: int = 20) -> str:
    """
    Detect market regime based on ATR relative to its moving average.

    Returns: 'TRENDING' or 'SIDEWAYS'

    Rule: If current ATR < (atr_sideways_threshold * MA of ATR) → SIDEWAYS
    Default threshold: 0.70 (configurable via ATR_SIDEWAYS_THRESHOLD in .env)
    """
    if len(candles) < ma_period + atr_period:
        return "TRENDING"  # Default to trending if insufficient data

    high = candles["high"]
    low = candles["low"]
    close = candles["close"]

    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(window=atr_period).mean()
    atr_ma = atr.rolling(window=ma_period).mean()

    current_atr = atr.iloc[-1]
    current_atr_ma = atr_ma.iloc[-1]

    if pd.isna(current_atr) or pd.isna(current_atr_ma) or current_atr_ma == 0:
        return "TRENDING"

    if current_atr < (settings.atr_sideways_threshold * current_atr_ma):
        return "SIDEWAYS"

    return "TRENDING"
