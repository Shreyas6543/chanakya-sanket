import pandas as pd


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def ema_bullish_alignment(close: pd.Series) -> bool:
    """
    EMA alignment: EMA9 > EMA21 > EMA50
    Indicates a bullish trending structure.
    """
    if len(close) < 50:
        return False
    ema9 = calculate_ema(close, 9)
    ema21 = calculate_ema(close, 21)
    ema50 = calculate_ema(close, 50)
    return float(ema9.iloc[-1]) > float(ema21.iloc[-1]) > float(ema50.iloc[-1])


def ema_bearish_alignment(close: pd.Series) -> bool:
    """
    Bearish EMA alignment: EMA9 < EMA21 < EMA50
    Indicates a bearish trending structure — mirror of ema_bullish_alignment.
    """
    if len(close) < 50:
        return False
    ema9 = calculate_ema(close, 9)
    ema21 = calculate_ema(close, 21)
    ema50 = calculate_ema(close, 50)
    return float(ema9.iloc[-1]) < float(ema21.iloc[-1]) < float(ema50.iloc[-1])


def price_above_ema(close: pd.Series, period: int = 21) -> bool:
    if len(close) < period:
        return False
    ema = calculate_ema(close, period)
    return float(close.iloc[-1]) > float(ema.iloc[-1])
