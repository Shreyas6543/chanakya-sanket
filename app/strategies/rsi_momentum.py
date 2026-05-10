import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.rsi import calculate_rsi, rsi_crossed_above
from app.indicators.ema import ema_bullish_alignment
from app.config import get_settings

settings = get_settings()


class RSIMomentumStrategy(BaseStrategy):
    name = "rsi_momentum"

    @property
    def max_points(self) -> int:
        return settings.points_rsi_momentum

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 50:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        rsi = calculate_rsi(candles["close"])
        crossed = rsi_crossed_above(rsi, level=settings.rsi_crossover_level)
        ema_aligned = ema_bullish_alignment(candles["close"])

        if crossed and ema_aligned:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"rsi": round(float(rsi.iloc[-1]), 2)},
            )
        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
