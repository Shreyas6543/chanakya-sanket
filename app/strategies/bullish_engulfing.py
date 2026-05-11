import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.vwap import calculate_vwap
from app.config import get_settings

settings = get_settings()


class BullishEngulfingStrategy(BaseStrategy):
    name = "bullish_engulfing"

    @property
    def max_points(self) -> int:
        return settings.points_bullish_engulfing

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 20:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        prev = candles.iloc[-2]
        curr = candles.iloc[-1]

        prev_bearish = float(prev["close"]) < float(prev["open"])
        curr_bullish = float(curr["close"]) > float(curr["open"])
        engulfs = (
            float(curr["open"]) <= float(prev["close"])
            and float(curr["close"]) >= float(prev["open"])
        )

        if not (prev_bearish and curr_bullish and engulfs):
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        vwap = calculate_vwap(candles)
        near_vwap = float(curr["low"]) <= float(vwap.iloc[-1]) * (1 + settings.vwap_tolerance_pct)

        if near_vwap:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"near_vwap": True},
            )

        # Bearish engulfing: prev candle bullish, curr candle bearish, engulfs prev, near VWAP
        prev_bullish = float(prev["close"]) > float(prev["open"])
        curr_bearish = float(curr["close"]) < float(curr["open"])
        bearish_engulfs = (
            float(curr["open"]) >= float(prev["close"])
            and float(curr["close"]) <= float(prev["open"])
        )
        if prev_bullish and curr_bearish and bearish_engulfs:
            near_vwap_bear = float(curr["high"]) >= float(vwap.iloc[-1]) * (1 - settings.vwap_tolerance_pct)
            if near_vwap_bear:
                return StrategySignal(
                    fired=True,
                    direction="PUT",
                    points=self.max_points,
                    reason=self.name,
                    details={"near_vwap": True},
                )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
