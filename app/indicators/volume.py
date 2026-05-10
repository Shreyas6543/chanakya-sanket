import pandas as pd


def volume_spike(candles: pd.DataFrame, period: int = 20, multiplier: float = 1.5) -> bool:
    """True if current candle volume > multiplier * average volume over last `period` candles."""
    if len(candles) < period + 1:
        return False
    avg_vol = float(candles["volume"].iloc[-(period + 1):-1].mean())
    current_vol = float(candles["volume"].iloc[-1])
    return avg_vol > 0 and current_vol > multiplier * avg_vol


def volume_spike_ratio(candles: pd.DataFrame, period: int = 20) -> float:
    """Returns current volume / average volume ratio."""
    if len(candles) < period + 1:
        return 1.0
    avg_vol = float(candles["volume"].iloc[-(period + 1):-1].mean())
    current_vol = float(candles["volume"].iloc[-1])
    return current_vol / avg_vol if avg_vol > 0 else 1.0
