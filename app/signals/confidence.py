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

    # Score formula: (fired_pts - unfired_penalty) / 60 * 100, capped at 100.
    #
    # unfired_penalty = sum(pts/10) for each evaluated strategy that did NOT fire.
    # The /10 factor is a small disagreement discount — unfired strategies slightly
    # reduce confidence but don't dominate the score.
    #
    # Denominator 60 is a fixed calibration constant (the old raw threshold):
    #   - VWAP+RSI+ORB fire, ST+PDH don't: (50 - 3.5) / 60×100 = 77%  → fires ✓
    #   - RSI+ORB only:                     (30 - 5.5) / 60×100 = 41%  → no fire ✓
    #   - VWAP+RSI+ORB+ST all fire:         (70 - 1.5) / 60×100 = 114% → capped 100% ✓
    #   - SIDEWAYS (RSI+ST max):            35 / 60×100 = 58%           → no fire ✓
    unfired_pts = sum(
        s.points for s in strategy_signals if not s.fired
    )
    unfired_penalty = unfired_pts / 10
    raw_with_penalty = raw_score - unfired_penalty
    score = max(0, min(100, round(raw_with_penalty / 60 * 100)))

    return ConfidenceResult(score=score, reasons=reasons, direction=direction)
