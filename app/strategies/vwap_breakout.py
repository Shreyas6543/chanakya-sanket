import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.vwap import vwap_breakout
from app.indicators.volume import volume_spike
from app.config import get_settings

settings = get_settings()


class VWAPBreakoutStrategy(BaseStrategy):
    name = "vwap_breakout"

    @property
    def max_points(self) -> int:
        return settings.points_vwap_breakout

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 20:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        breakout = vwap_breakout(candles)
        vol_spike = volume_spike(candles, multiplier=settings.volume_spike_multiplier)

        if breakout and vol_spike:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"vol_spike": True},
            )
        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
