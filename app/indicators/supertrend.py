"""
Supertrend indicator.

Parameters:
  period     — ATR lookback (default 10)
  multiplier — band width factor (default 3.0)

Returns a DataFrame with columns:
  supertrend  — the trailing stop value
  direction   — +1 for bullish (close > supertrend), -1 for bearish
"""
import numpy as np
import pandas as pd

from app.indicators.atr import calculate_atr


def calculate_supertrend(
    candles: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    atr = calculate_atr(candles, period=period)
    hl2 = (candles["high"] + candles["low"]) / 2

    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    n = len(candles)
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction = pd.Series(np.ones(n, dtype=int), index=candles.index)
    supertrend = pd.Series(np.zeros(n), index=candles.index)

    close = candles["close"]

    for i in range(1, n):
        # Final upper band
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        # Final lower band
        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        # Direction
        if direction.iloc[i - 1] == -1 and close.iloc[i] > final_upper.iloc[i]:
            direction.iloc[i] = 1   # flipped bullish
        elif direction.iloc[i - 1] == 1 and close.iloc[i] < final_lower.iloc[i]:
            direction.iloc[i] = -1  # flipped bearish
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        # Supertrend value
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    # First row
    supertrend.iloc[0] = final_lower.iloc[0] if direction.iloc[0] == 1 else final_upper.iloc[0]

    return pd.DataFrame({"supertrend": supertrend, "direction": direction}, index=candles.index)
