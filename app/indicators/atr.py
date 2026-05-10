import pandas as pd


def calculate_atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    high = candles["high"]
    low = candles["low"]
    close = candles["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(window=period).mean()


def current_atr(candles: pd.DataFrame, period: int = 14) -> float:
    atr = calculate_atr(candles, period)
    val = atr.iloc[-1]
    return float(val) if not pd.isna(val) else 0.0
