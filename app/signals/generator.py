import structlog
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Signal, SignalDirection, MarketRegime, StrategyResult
from app.strategies.vwap_breakout import VWAPBreakoutStrategy
from app.strategies.rsi_momentum import RSIMomentumStrategy
from app.strategies.opening_range import OpeningRangeBreakoutStrategy
from app.strategies.oi_buildup import OIBuildupStrategy
from app.signals.confidence import calculate_confidence
from app.signals.strike_selector import select_strike, select_expiry
from app.signals.lifecycle import get_open_signal_count
from app.utils.regime import detect_regime
from app.utils.market_hours import can_generate_signals

logger = structlog.get_logger()
settings = get_settings()

# BullishEngulfing removed — backtested 14.3% win rate vs 33.3% break-even (6-week data)
STRATEGIES = [
    VWAPBreakoutStrategy(),
    RSIMomentumStrategy(),
    OpeningRangeBreakoutStrategy(),
    OIBuildupStrategy(),
]

# Breakout strategies suppressed in sideways markets
BREAKOUT_STRATEGIES = {"vwap_breakout", "opening_range_breakout"}


async def generate_signal(
    symbol: str,
    candles: pd.DataFrame,
    spot_price: float,
    oi_data: dict | None,
    sentiment_label: str | None,
    session: AsyncSession,
    force: bool = False,
    source: str = "live",
) -> Signal | None:
    """
    Main signal generation pipeline for one symbol.
    Returns a Signal DB object if signal generated and saved, else None.
    force=True bypasses the market hours check (for testing).
    """
    if not force and not can_generate_signals():
        return None

    regime = detect_regime(candles)
    is_sideways = regime == "SIDEWAYS"

    strategy_results = []
    for strategy in STRATEGIES:
        if is_sideways and strategy.name in BREAKOUT_STRATEGIES:
            continue
        result = strategy.evaluate(candles, oi_data)
        strategy_results.append(result)

    confidence = calculate_confidence(strategy_results, sentiment_label)

    if confidence.score < settings.min_confidence_score:
        return None

    if confidence.direction is None:
        return None

    # Check concurrent signal limit
    open_count = await get_open_signal_count(symbol, confidence.direction, session)
    if open_count >= settings.max_open_signals_per_symbol:
        logger.info(
            "Signal suppressed — max concurrent signals reached",
            symbol=symbol,
            direction=confidence.direction,
        )
        return None

    strike = select_strike(spot_price, symbol, confidence.score)
    expiry = select_expiry(symbol)

    # Entry, SL, Target
    # NOTE: entry/sl/target are INDEX levels (spot price), not option premiums.
    # Option premium is estimated separately for capital sizing.
    from app.indicators.atr import current_atr
    atr = current_atr(candles)
    entry = spot_price
    if confidence.direction == "CALL":
        stop_loss = round(entry - atr, 2)
        target = round(entry + (2 * atr), 2)
    else:
        stop_loss = round(entry + atr, 2)
        target = round(entry - (2 * atr), 2)

    # Lot sizes from config (NSE can change these)
    lot_size = settings.nifty_lot_size if symbol.upper() == "NIFTY" else settings.banknifty_lot_size

    # Option premium estimate (used for capital sizing only)
    # ATM weekly option premium ≈ ATR × multiplier (rough approximation until live options data)
    estimated_premium = round(atr * settings.premium_atr_multiplier, 2) if atr > 0 else round(spot_price * 0.004, 2)

    # Capital & lot sizing — based on PREMIUM paid, not notional value
    sl_loss_per_lot = estimated_premium * settings.premium_sl_loss_ratio * lot_size
    lots_by_risk = max(1, int(settings.risk_amount / sl_loss_per_lot)) if sl_loss_per_lot > 0 else 1

    premium_per_lot = estimated_premium * lot_size
    lots_by_capital = max(1, int(settings.max_capital_per_trade / premium_per_lot)) if premium_per_lot > 0 else 1

    suggested_lots = min(lots_by_risk, lots_by_capital)
    capital_required = round(estimated_premium * suggested_lots * lot_size, 2)

    signal = Signal(
        symbol=symbol,
        direction=SignalDirection(confidence.direction),
        strike=strike,
        expiry=expiry,
        entry=entry,
        stop_loss=stop_loss,
        target=target,
        confidence=confidence.score,
        reasons=confidence.reasons,
        regime=MarketRegime(regime),
        capital_required=capital_required,
        suggested_lots=suggested_lots,
        source=source,
    )
    session.add(signal)
    await session.flush()

    # Record which strategies fired so by_reason analytics works
    for result in strategy_results:
        if result.fired:
            session.add(StrategyResult(
                signal_id=signal.id,
                strategy_name=result.reason,
                contributed_points=result.points,
                fired=True,
            ))

    logger.info(
        "Signal generated",
        symbol=symbol,
        direction=confidence.direction,
        confidence=confidence.score,
        strike=strike,
        expiry=expiry,
    )
    return signal
