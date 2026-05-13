"""
Previous Day High / Low Breakout strategy.

Logic:
  - Previous day high (PDH): max(high) of all candles from the prior trading day.
  - Previous day low  (PDL): min(low)  of all candles from the prior trading day.

Signal fires on a CROSSOVER:
  - CALL: previous candle close was <= PDH AND current candle close > PDH  (fresh breakout above PDH)
  - PUT:  previous candle close was >= PDL AND current candle close < PDL  (fresh breakdown below PDL)

Requires candles to span at least two trading days.
The candle DataFrame must have a 'timestamp' column OR a DatetimeIndex.
+15 pts.
"""
import pandas as pd
from app.strategies.base import BaseStrategy, StrategySignal
from app.config import get_settings

settings = get_settings()


def _get_timestamps(candles: pd.DataFrame) -> pd.Series:
    """Return a Series of timestamps, regardless of whether stored in index or column."""
    if "timestamp" in candles.columns:
        return pd.to_datetime(candles["timestamp"], utc=True)
    if isinstance(candles.index, pd.DatetimeIndex):
        return candles.index.to_series().reset_index(drop=True)
    return None


class PDHPDLStrategy(BaseStrategy):
    name = "pdh_pdl"

    @property
    def max_points(self) -> int:
        return settings.points_pdh_pdl

    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        if len(candles) < 10:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        ts = _get_timestamps(candles)
        if ts is None:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        # Normalise to IST date
        try:
            from datetime import timezone, timedelta
            IST = timezone(timedelta(hours=5, minutes=30))
            dates = ts.dt.tz_convert(IST).dt.date if ts.dt.tz is not None else ts.dt.date
        except Exception:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        unique_dates = sorted(dates.unique())
        if len(unique_dates) < 2:
            # All candles are from the same day — no previous day reference
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        today = unique_dates[-1]
        prev_day = unique_dates[-2]

        prev_mask = dates == prev_day
        if not prev_mask.any():
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        pdh = float(candles.loc[prev_mask.values, "high"].max())
        pdl = float(candles.loc[prev_mask.values, "low"].min())

        today_mask = dates == today
        today_candles = candles.loc[today_mask.values]
        if len(today_candles) < 2:
            return StrategySignal(fired=False, direction=None, points=0, reason=self.name)

        prev_close = float(today_candles["close"].iloc[-2])
        curr_close = float(today_candles["close"].iloc[-1])

        if prev_close <= pdh and curr_close > pdh:
            return StrategySignal(
                fired=True,
                direction="CALL",
                points=self.max_points,
                reason=self.name,
                details={"pdh": pdh, "close": curr_close},
            )

        if prev_close >= pdl and curr_close < pdl:
            return StrategySignal(
                fired=True,
                direction="PUT",
                points=self.max_points,
                reason=self.name,
                details={"pdl": pdl, "close": curr_close},
            )

        return StrategySignal(fired=False, direction=None, points=0, reason=self.name)
