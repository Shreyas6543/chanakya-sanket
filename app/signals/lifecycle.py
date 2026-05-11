import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from app.db.models import Signal, SignalOutcome, SignalState
from app.utils.market_hours import is_eod, now_ist

logger = structlog.get_logger()


async def evaluate_signal_tick(
    signal: Signal,
    current_price: float,
    session: AsyncSession,
) -> str | None:
    """
    Called on every price tick for open signals.
    Returns new state if changed, else None.
    """
    if signal.state != SignalState.OPEN:
        return None

    new_state = None

    if signal.direction.value == "CALL":
        if current_price >= signal.target:
            new_state = SignalState.TARGET_HIT
        elif current_price <= signal.stop_loss:
            new_state = SignalState.SL_HIT
    else:  # PUT — target is below entry, stop_loss is above entry
        if current_price <= signal.target:
            new_state = SignalState.TARGET_HIT
        elif current_price >= signal.stop_loss:
            new_state = SignalState.SL_HIT

    if new_state:
        await _close_signal(signal, new_state, current_price, session)
        return new_state.value

    return None


async def expire_eod_signals(session: AsyncSession):
    """Auto-expire all OPEN signals at market close."""
    if not is_eod():
        return

    result = await session.execute(
        select(Signal).where(Signal.state == SignalState.OPEN)
    )
    open_signals = result.scalars().all()

    for signal in open_signals:
        await _close_signal(signal, SignalState.EXPIRED, None, session)
        logger.info("Signal expired at EOD", signal_id=signal.id, symbol=signal.symbol)


async def _close_signal(
    signal: Signal,
    new_state: SignalState,
    exit_price: float | None,
    session: AsyncSession,
):
    signal.state = new_state
    signal.evaluated_at = now_ist()

    pnl = None
    result_label = new_state.value

    if exit_price is not None:
        if signal.direction.value == "CALL":
            pnl = (exit_price - signal.entry) * signal.suggested_lots
        else:
            pnl = (signal.entry - exit_price) * signal.suggested_lots

    outcome = SignalOutcome(
        signal_id=signal.id,
        result=result_label,
        pnl=pnl,
        evaluated_at=now_ist(),
    )
    session.add(outcome)
    logger.info(
        "Signal closed",
        signal_id=signal.id,
        symbol=signal.symbol,
        state=new_state.value,
        pnl=pnl,
    )


async def get_open_signal_count(symbol: str, direction: str, session: AsyncSession) -> int:
    result = await session.execute(
        select(Signal).where(
            Signal.symbol == symbol,
            Signal.direction == direction,
            Signal.state == SignalState.OPEN,
        )
    )
    return len(result.scalars().all())
