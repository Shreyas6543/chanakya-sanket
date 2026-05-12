import pandas as pd
from app.config import get_settings

settings = get_settings()


def detect_regime(candles: pd.DataFrame, atr_period: int = 14, ma_period: int = 20) -> str:
    """
    Detect market regime using ATR + CPR (Central Pivot Range).

    Returns: 'TRENDING' or 'SIDEWAYS'

    Rules:
    1. CPR narrow (< 0.15% of pivot): prior day was indecisive → SIDEWAYS
       (Zerodha Varsity: narrow CPR = expect range-bound day)
    2. ATR < threshold × ATR_MA: low volatility → SIDEWAYS
    3. Either condition alone is sufficient to call SIDEWAYS.
       Both trending = TRENDING.
    """
    if len(candles) < ma_period + atr_period:
        return "TRENDING"

    # --- CPR regime check ---
    try:
        from app.indicators.cpr import calculate_cpr
        cpr = calculate_cpr(candles)
        if cpr is not None and cpr.is_narrow:
            return "SIDEWAYS"
    except Exception:
        pass  # CPR unavailable — fall through to ATR check

    # --- ATR regime check ---
    high = candles["high"]
    low = candles["low"]
    close = candles["close"]

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


def trend_efficiency(candles: pd.DataFrame) -> float:
    """
    Kaufman Efficiency Ratio: net directional move / total price path.

    Range: 0.0 (pure chop) → 1.0 (perfect trend).
    A value < 0.5 means the market has been going back-and-forth more than forward —
    breakout signals on such days tend to be false and reverse immediately.

    Formula: abs(close[-1] - close[0]) / (high.max() - low.min())
    Uses the full candle window passed in (typically the 50-100 candle buffer).
    """
    if len(candles) < 10:
        return 1.0  # Not enough data — don't filter

    net_move = abs(float(candles["close"].iloc[-1]) - float(candles["close"].iloc[0]))
    total_range = float(candles["high"].max()) - float(candles["low"].min())

    if total_range == 0:
        return 1.0

    return round(net_move / total_range, 3)
