"""
Adaptive hour-based alert filter using rolling win rate.

Problem it solves
-----------------
Hard-blocking bad hours creates a dead zone where the system can never learn
whether the hour has recovered.  This filter suppresses Telegram alerts for
consistently poor hours while continuing to save every signal to the DB and
evaluate its outcome.  Because the lifecycle evaluator runs unconditionally,
the rolling WR updates automatically — a recovering hour will cross the
re-enable threshold on its own with no manual intervention.

Tiers  (computed from last ROLLING_WINDOW live closed signals for the hour)
---------------------------------------------------------------------------
  ALERT    – Telegram sent normally    (WR >= WARN_BELOW, or < MIN_SAMPLES)
  WARN     – Telegram sent with ⚠️ tag  (WR in [SUPPRESS_BELOW, WARN_BELOW))
  SUPPRESS – Telegram skipped          (WR < SUPPRESS_BELOW, sample >= MIN_SAMPLES)

Hysteresis
----------
Disable threshold (SUPPRESS_BELOW = 30 %) is intentionally below the
re-enable threshold (WARN_BELOW = 40 %).  This prevents flip-flopping when
an hour's WR is sitting right at the edge.

Only live signals count
-----------------------
Mock and historical signals are excluded so backtests and test triggers
never pollute the filter's posterior.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Public tier constants
ALERT    = "ALERT"
WARN     = "WARN"
SUPPRESS = "SUPPRESS"

# Thresholds
MIN_SAMPLES    = 15    # Never suppress an hour with fewer samples than this
SUPPRESS_BELOW = 30.0  # WR% — suppress Telegram below this
WARN_BELOW     = 40.0  # WR% — warn (but still alert) below this
ROLLING_WINDOW = 20    # Evaluate the most recent N closed signals for the hour


async def get_hour_tier(hour: int, session: AsyncSession) -> tuple[str, float | None]:
    """
    Return (tier, rolling_wr_pct) for a trading hour.

    rolling_wr_pct is None when sample < MIN_SAMPLES (tier will be ALERT).

    The session must be the same async session in use by the caller so we
    can read already-flushed (but not yet committed) data if needed.
    """
    from app.db.models import Signal, SignalState  # local import avoids circular

    closed_states = [
        SignalState.TARGET_HIT,
        SignalState.SL_HIT,
        SignalState.EXPIRED,
        SignalState.USER_CLOSED,
    ]

    # Fetch recent closed real signals (live + historical backfill).
    # Excluding mock/test signals keeps the filter grounded in real market data.
    # Including "historical" means a walk-forward backfill naturally bootstraps:
    # no data → ALERT for the first few months, rolling window fills, then
    # the filter starts suppressing bad hours — same behaviour as going live.
    result = await session.execute(
        select(Signal)
        .where(Signal.state.in_(closed_states))
        .where(Signal.source.in_(["live", "historical"]))
        .order_by(Signal.created_at.desc())
        .limit(300)
    )
    recent = result.scalars().all()

    # Filter to this hour in Python — avoids JSONB casting in SQL and is
    # fast enough given the 300-row cap.
    hour_signals = [
        s for s in recent
        if (s.signal_context or {}).get("hour") == hour
    ][:ROLLING_WINDOW]

    n = len(hour_signals)

    if n < MIN_SAMPLES:
        logger.debug("hour_filter: insufficient data — not suppressing", hour=hour, n=n)
        return (ALERT, None)

    wins = sum(1 for s in hour_signals if s.state == SignalState.TARGET_HIT)
    wr   = round((wins / n) * 100, 1)

    if wr < SUPPRESS_BELOW:
        tier = SUPPRESS
    elif wr < WARN_BELOW:
        tier = WARN
    else:
        tier = ALERT

    logger.info(
        "hour_filter evaluated",
        hour=hour,
        tier=tier,
        rolling_wr=wr,
        sample_size=n,
    )
    return (tier, wr)
