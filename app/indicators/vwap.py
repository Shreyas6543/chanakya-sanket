import pandas as pd


def calculate_vwap(candles: pd.DataFrame) -> pd.Series:
    """
    VWAP resets every trading day.
    Expects columns: high, low, close, volume, timestamp
    """
    typical_price = (candles["high"] + candles["low"] + candles["close"]) / 3
    cumulative_vol = candles["volume"].cumsum()
    # Index instruments (NSE_INDEX) have no volume — fall back to simple TP average
    if float(cumulative_vol.iloc[-1]) == 0:
        return typical_price.expanding().mean()
    cumulative_tp_vol = (typical_price * candles["volume"]).cumsum()
    return cumulative_tp_vol / cumulative_vol


def price_above_vwap(candles: pd.DataFrame) -> bool:
    if len(candles) < 2:
        return False
    vwap = calculate_vwap(candles)
    return float(candles["close"].iloc[-1]) > float(vwap.iloc[-1])


def vwap_breakout(candles: pd.DataFrame) -> bool:
    """Price crossed above VWAP on the last candle."""
    if len(candles) < 2:
        return False
    vwap = calculate_vwap(candles)
    prev_close = float(candles["close"].iloc[-2])
    curr_close = float(candles["close"].iloc[-1])
    prev_vwap = float(vwap.iloc[-2])
    curr_vwap = float(vwap.iloc[-1])
    return prev_close <= prev_vwap and curr_close > curr_vwap


def vwap_breakdown(candles: pd.DataFrame) -> bool:
    """Price crossed below VWAP on the last candle — mirror of vwap_breakout for PUT signals."""
    if len(candles) < 2:
        return False
    vwap = calculate_vwap(candles)
    prev_close = float(candles["close"].iloc[-2])
    curr_close = float(candles["close"].iloc[-1])
    prev_vwap = float(vwap.iloc[-2])
    curr_vwap = float(vwap.iloc[-1])
    return prev_close >= prev_vwap and curr_close < curr_vwap
