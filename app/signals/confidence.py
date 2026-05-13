from dataclasses import dataclass
from app.strategies.base import StrategySignal
from app.config import get_settings

settings = get_settings()


@dataclass
class ConfidenceResult:
    score: int
    reasons: dict[str, int]   # {reason_name: points}
    direction: str | None     # "CALL" or "PUT" — must be unanimous or majority


def calculate_confidence(
    strategy_signals: list[StrategySignal],
    sentiment_label: str | None = None,
    points_vwap: int | None = None,
    points_rsi: int | None = None,
    points_oi: int | None = None,
    points_orb: int | None = None,
) -> ConfidenceResult:
    """
    Aggregate strategy signals into a confidence score.
    Only fires if all fired strategies agree on direction.
    Sentiment adds bonus points if aligned.
    """
    fired = [s for s in strategy_signals if s.fired]

    if len(fired) < 2:
        # Require at least 2 strategies to agree — prevents single-strategy noise.
        # In SIDEWAYS mode with OI unavailable, only RSI can fire; single RSI is not enough.
        return ConfidenceResult(score=0, reasons={}, direction=None)

    # Direction must be unanimous among fired strategies
    directions = {s.direction for s in fired}
    if len(directions) > 1:
        return ConfidenceResult(score=0, reasons={}, direction=None)

    direction = directions.pop()

    # Apply per-run point overrides (used for grid search / backtesting experiments)
    overrides = {
        "vwap_breakout":          points_vwap,
        "rsi_momentum":           points_rsi,
        "oi_buildup":             points_oi,
        "opening_range_breakout": points_orb,
    }
    reasons: dict[str, int] = {
        s.reason: (overrides.get(s.reason) if overrides.get(s.reason) is not None else s.points)
        for s in fired
    }
    raw_score = sum(reasons.values())

    # Sentiment bonus
    if sentiment_label == "BULLISH" and direction == "CALL":
        reasons["positive_sentiment"] = settings.points_positive_sentiment
        raw_score += settings.points_positive_sentiment
    elif sentiment_label == "BEARISH" and direction == "PUT":
        reasons["negative_sentiment"] = settings.points_positive_sentiment
        raw_score += settings.points_positive_sentiment

    # Normalize score to 0-100 based on max possible from strategies actually evaluated.
    # Only strategies present in strategy_signals count toward the denominator.
    # Sentiment only counts when sentiment_label is not None (otherwise it can never contribute).
    # This keeps the 60-point threshold meaningful in all modes:
    #   - Backfill (VWAP+RSI+ORB, no OI, no sentiment): max=50 → RSI+ORB (30pts) = 60% → fires
    #   - Live (all 4 strategies + possible sentiment): max=75 → 3 strategies needed for 60%
    strategy_names = {s.reason for s in strategy_signals}
    all_strategy_pts = {
        "vwap_breakout":          settings.points_vwap_breakout,
        "rsi_momentum":           settings.points_rsi_momentum,
        "opening_range_breakout": settings.points_opening_range,
        "oi_buildup":             settings.points_oi_buildup,
        "supertrend":             settings.points_supertrend,
        "pdh_pdl":                settings.points_pdh_pdl,
    }
    max_possible = sum(pts for name, pts in all_strategy_pts.items() if name in strategy_names)
    if sentiment_label is not None:
        max_possible += settings.points_positive_sentiment

    score = round(raw_score / max_possible * 100) if max_possible > 0 else 0

    return ConfidenceResult(score=score, reasons=reasons, direction=direction)
