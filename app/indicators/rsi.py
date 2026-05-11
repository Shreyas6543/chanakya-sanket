import pandas as pd


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def rsi_crossed_above(rsi: pd.Series, level: float = 55, lookback: int = 5) -> bool:
    """
    True if RSI crossed above `level` within the last `lookback` candles.
    Lookback of 5 (25 minutes) allows strategies to align with other signals
    that fire after the RSI crossover happens.
    """
    if len(rsi) < 2:
        return False
    window = rsi.iloc[-(lookback + 1):]
    for i in range(len(window) - 1):
        if float(window.iloc[i]) < level <= float(window.iloc[i + 1]):
            return True
    return False


def rsi_is_oversold(rsi: pd.Series, level: float = 35) -> bool:
    return len(rsi) > 0 and float(rsi.iloc[-1]) < level
