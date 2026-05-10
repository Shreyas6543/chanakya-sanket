import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.volume import volume_spike
from app.config import get_settings

settings = get_settings()


class OpeningRangeBreakoutStrategy(BaseStrategy):
    name = "opening_range_breakout"

    @property
    def max_points(self) -> int:
        return settings.points_opening_range

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 4:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        opening_range = candles.iloc[:3]
        or_high = float(opening_range["high"].max())
        or_low = float(opening_range["low"].min())

        curr = candles.iloc[-1]
        curr_close = float(curr["close"])

        bullish_breakout = curr_close > or_high
        bearish_breakout = curr_close < or_low

        if not (bullish_breakout or bearish_breakout):
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        if not volume_spike(candles, multiplier=settings.volume_spike_multiplier):
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        direction = "CALL" if bullish_breakout else "PUT"
        return StrategySignal(
            fired=True,
            direction=direction,
            points=self.max_points,
            reason=self.name,
            details={"or_high": or_high, "or_low": or_low},
        )
