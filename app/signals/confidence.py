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

    if not fired:
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
    score = sum(reasons.values())

    # Sentiment bonus
    if sentiment_label == "BULLISH" and direction == "CALL":
        reasons["positive_sentiment"] = settings.points_positive_sentiment
        score += settings.points_positive_sentiment
    elif sentiment_label == "BEARISH" and direction == "PUT":
        reasons["negative_sentiment"] = settings.points_positive_sentiment
        score += settings.points_positive_sentiment

    return ConfidenceResult(score=score, reasons=reasons, direction=direction)
