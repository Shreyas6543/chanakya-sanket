import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.indicators.rsi import calculate_rsi, rsi_crossed_above, rsi_crossed_below
from app.indicators.ema import ema_bullish_alignment, ema_bearish_alignment
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
        current_rsi = float(rsi.iloc[-1])
        crossed = rsi_crossed_above(rsi, level=settings.rsi_crossover_level)
        ema_aligned = ema_bullish_alignment(candles["close"])

        # Zerodha Varsity: RSI stuck overbought (>70 for 5+ candles) = trend continuation,
        # NOT a sell signal. Treat as additional bullish confirmation.
        rsi_stuck_overbought = (rsi.iloc[-5:] > 70).all() if len(rsi) >= 5 else False

        if ema_aligned and (crossed or rsi_stuck_overbought):
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"rsi": round(current_rsi, 2), "stuck_overbought": rsi_stuck_overbought},
            )

        crossed_below = rsi_crossed_below(rsi, level=settings.rsi_crossover_level - 10)
        ema_bearish = ema_bearish_alignment(candles["close"])
        rsi_stuck_oversold = (rsi.iloc[-5:] < 30).all() if len(rsi) >= 5 else False

        if ema_bearish and (crossed_below or rsi_stuck_oversold):
            return StrategySignal(
                fired=True,
                direction="PUT",
                points=self.max_points,
                reason=self.name,
                details={"rsi": round(current_rsi, 2), "stuck_oversold": rsi_stuck_oversold},
            )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
