import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.config import get_settings

settings = get_settings()


class OIBuildupStrategy(BaseStrategy):
    name = "oi_buildup"

    @property
    def max_points(self) -> int:
        return settings.points_oi_buildup

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if not oi_data:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        call_oi = oi_data.get("call_oi", 0)
        put_oi = oi_data.get("put_oi", 0)
        prev_call_oi = oi_data.get("prev_call_oi", 0)
        prev_put_oi = oi_data.get("prev_put_oi", 0)

        if prev_call_oi == 0 or prev_put_oi == 0:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        threshold = settings.oi_buildup_threshold

        call_oi_buildup = call_oi > prev_call_oi * (1 + threshold)
        call_oi_unwind  = call_oi < prev_call_oi * (1 - threshold)
        put_oi_buildup  = put_oi  > prev_put_oi  * (1 + threshold)
        put_oi_unwind   = put_oi  < prev_put_oi  * (1 - threshold)

        if len(candles) < 2:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        price_breakout  = float(candles["close"].iloc[-1]) > float(candles["close"].iloc[-2])
        price_breakdown = float(candles["close"].iloc[-1]) < float(candles["close"].iloc[-2])

        call_oi_change = round(call_oi / prev_call_oi - 1, 3)
        put_oi_change  = round(put_oi  / prev_put_oi  - 1, 3)

        # CALL signal: long buildup (strong) or short covering (weak)
        # Long buildup  = call OI ↑ + price ↑ → new money, full points
        # Short covering = put OI ↓ + price ↑ → exits only, half points
        if price_breakout and not put_oi_buildup:
            if call_oi_buildup:
                # Long buildup — strongest signal (new conviction entering)
                points = self.max_points
                scenario = "long_buildup"
            elif put_oi_unwind:
                # Short covering — weaker signal (pain-driven, no new money)
                points = self.max_points // 2
                scenario = "short_covering"
            else:
                points = None

            if points is not None:
                return StrategySignal(
                    fired=True, direction="CALL", points=points, reason=self.name,
                    details={"scenario": scenario, "call_oi_change": call_oi_change, "put_oi_change": put_oi_change},
                )

        # PUT signal: short buildup (strong) or long unwinding (weak)
        # Short buildup  = put OI ↑ + price ↓ → new money, full points
        # Long unwinding = call OI ↓ + price ↓ → exits only, half points
        if price_breakdown and not call_oi_buildup:
            if put_oi_buildup:
                # Short buildup — strongest bearish signal
                points = self.max_points
                scenario = "short_buildup"
            elif call_oi_unwind:
                # Long unwinding — weaker bearish signal
                points = self.max_points // 2
                scenario = "long_unwinding"
            else:
                points = None

            if points is not None:
                return StrategySignal(
                    fired=True, direction="PUT", points=points, reason=self.name,
                    details={"scenario": scenario, "call_oi_change": call_oi_change, "put_oi_change": put_oi_change},
                )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
