"""
Adaptive hour-based shadow filter.

Signals are ALWAYS generated and saved to DB — no hour is ever blocked.
This function decides whether a signal should be "shadowed" (no Telegram alert,
source tagged as 'shadow') based on the rolling win rate for that hour.

Rule: WR < SHADOW_THRESHOLD (40%) AND sample >= MIN_SAMPLES → shadow
      WR >= 40% OR insufficient data                         → normal (send Telegram)

Using 'shadow' as the source tag (instead of a boolean flag) lets the frontend
filter and render shadow signals separately while the analytics engine
naturally excludes them from performance stats.

Including 'historical' signals in the rolling WR query means a walk-forward
backfill bootstraps the filter correctly: no data → never shadows for the first
few months, then the window fills and bad hours start getting suppressed.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

SHADOW_THRESHOLD = 40.0   # WR% — shadow when rolling WR falls below this
MIN_SAMPLES      = 15     # Never shadow with fewer samples (insufficient evidence)
ROLLING_WINDOW   = 20     # Evaluate the most recent N closed signals for this hour


async def should_shadow(hour: int, session: AsyncSession) -> tuple[bool, float | None]:
    """
    Return (is_shadow, rolling_wr_pct) for a trading hour.

    is_shadow=True  → set signal.source='shadow', skip Telegram
    is_shadow=False → keep source as-is, send Telegram normally

    rolling_wr_pct is None when sample < MIN_SAMPLES.
    """
    from app.db.models import Signal, SignalState  # local import avoids circular

    closed_states = [
        SignalState.TARGET_HIT,
        SignalState.SL_HIT,
        SignalState.EXPIRED,
        SignalState.USER_CLOSED,
    ]

    # Include live, historical, AND shadow — all three have real market outcomes
    # (the lifecycle evaluator runs on every signal regardless of source).
    # Shadow signals represent what would have happened if we had traded that hour,
    # so they carry genuine WR information and should influence the filter.
    # Only mock/test signals are excluded — they use artificial price data.
    result = await session.execute(
        select(Signal)
        .where(Signal.state.in_(closed_states))
        .where(Signal.source.in_(["live", "historical", "shadow"]))
        .order_by(Signal.created_at.desc())
        .limit(300)
    )
    recent = result.scalars().all()

    # Filter to this hour in Python (avoids JSONB casting complexity in SQL).
    # Note: shadow signals keep their original_source in signal_context, but their
    # source column is 'shadow', so they are excluded from this query — correct,
    # because we want the filter to learn only from signals that were actually traded.
    hour_signals = [
        s for s in recent
        if (s.signal_context or {}).get("hour") == hour
    ][:ROLLING_WINDOW]

    n = len(hour_signals)

    if n < MIN_SAMPLES:
        logger.debug("hour_filter: insufficient data — not shadowing", hour=hour, n=n)
        return (False, None)

    wins = sum(1 for s in hour_signals if s.state == SignalState.TARGET_HIT)
    wr   = round((wins / n) * 100, 1)
    is_shadow = wr < SHADOW_THRESHOLD

    logger.info(
        "hour_filter evaluated",
        hour=hour,
        is_shadow=is_shadow,
        rolling_wr=wr,
        sample_size=n,
    )
    return (is_shadow, wr)
