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

        # CALL signal: call OI building up OR put OI unwinding — with price confirmation
        # (either leg alone is sufficient for daily EOD data; intraday data may show both)
        if (call_oi_buildup or put_oi_unwind) and price_breakout and not put_oi_buildup:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={
                    "call_oi_change": round(call_oi / prev_call_oi - 1, 3),
                    "put_oi_change":  round(put_oi  / prev_put_oi  - 1, 3),
                },
            )

        # PUT signal: put OI building up OR call OI unwinding — with price confirmation
        if (put_oi_buildup or call_oi_unwind) and price_breakdown and not call_oi_buildup:
            return StrategySignal(
                fired=True,
                direction="PUT",
                points=self.max_points,
                reason=self.name,
                details={
                    "call_oi_change": round(call_oi / prev_call_oi - 1, 3),
                    "put_oi_change":  round(put_oi  / prev_put_oi  - 1, 3),
                },
            )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
