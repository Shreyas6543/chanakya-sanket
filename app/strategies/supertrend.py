"""
Supertrend crossover strategy.

Fires on the candle where Supertrend flips direction:
  bearish → bullish  → CALL  (+20 pts)
  bullish → bearish  → PUT   (+20 pts)

Requires at least 20 candles for ATR warm-up.
"""
import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.supertrend import calculate_supertrend
from app.config import get_settings

settings = get_settings()


class SupertrendStrategy(BaseStrategy):
    name = "supertrend"

    @property
    def max_points(self) -> int:
        return settings.points_supertrend

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 20:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        st = calculate_supertrend(candles)
        directions = st["direction"]

        prev_dir = int(directions.iloc[-2])
        curr_dir = int(directions.iloc[-1])

        if prev_dir == -1 and curr_dir == 1:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"prev_direction": "bearish", "curr_direction": "bullish"},
            )
        if prev_dir == 1 and curr_dir == -1:
            return StrategySignal(
                fired=True,
                direction="PUT",
                points=self.max_points,
                reason=self.name,
                details={"prev_direction": "bullish", "curr_direction": "bearish"},
            )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
