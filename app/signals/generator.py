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

# BullishEngulfing removed — backtested 14.3% win rate vs 33.3% break-even (6-week data).
# All other strategies retained at original weights — confirmed best on 6-month backtest:
# VWAP=20, RSI=15, OI=30, ORB=15, min=60 → 44.8% WR on 512 signals (Nov 2025–May 2026).
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
    min_confidence: int | None = None,
    points_vwap: int | None = None,
    points_rsi: int | None = None,
    points_oi: int | None = None,
    points_orb: int | None = None,
    target_multiplier: float | None = None,
    sl_multiplier: float | None = None,
) -> Signal | None:
    """
    Main signal generation pipeline for one symbol.
    Returns a Signal DB object if signal generated and saved, else None.
    force=True bypasses the market hours check (for testing).
    """
    if not force and not can_generate_signals():
        return None

    # Block signals after 13:30 IST — WR drops sharply (14:xx=25.7%, 15:xx=11.8%)
    # Break-even for 2:1 R:R is 33.3%. Only 10–13:xx is consistently above break-even.
    from app.utils.market_hours import now_ist
    _now = now_ist()
    if not force and (_now.hour >= 14 or (_now.hour == 13 and _now.minute >= 30)):
        return None

    regime = detect_regime(candles)
    is_sideways = regime == "SIDEWAYS"


    strategy_results = []
    for strategy in STRATEGIES:
        if is_sideways and strategy.name in BREAKOUT_STRATEGIES:
            continue
        if oi_data is None and strategy.name == "oi_buildup":
            continue  # Skip OI strategy when data unavailable — keeps max_possible accurate
        result = strategy.evaluate(candles, oi_data)
        strategy_results.append(result)

    confidence = calculate_confidence(
        strategy_results, sentiment_label,
        points_vwap=points_vwap, points_rsi=points_rsi,
        points_oi=points_oi, points_orb=points_orb,
    )

    threshold = min_confidence if min_confidence is not None else settings.min_confidence_score
    if confidence.score < threshold:
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

    strike = select_strike(spot_price, symbol, confidence.score, confidence.direction)
    expiry = select_expiry(symbol)

    # Entry, SL, Target
    # NOTE: entry/sl/target are INDEX levels (spot price), not option premiums.
    # Option premium is estimated separately for capital sizing.
    from app.indicators.atr import current_atr
    from app.indicators.rsi import calculate_rsi
    from app.indicators.vwap import calculate_vwap
    atr = current_atr(candles)

    # Build signal context snapshot — market conditions at this exact moment
    _vwap_series = calculate_vwap(candles)
    _vwap_val = float(_vwap_series.iloc[-1])
    _rsi_val = float(calculate_rsi(candles["close"]).iloc[-1])
    _vwap_dist_pct = round((spot_price - _vwap_val) / _vwap_val * 100, 3) if _vwap_val else 0

    # Extract signal timestamp — handle both DatetimeIndex and RangeIndex+timestamp column
    _sig_ts = None
    if "timestamp" in candles.columns:
        _sig_ts = candles["timestamp"].iloc[-1]
    elif hasattr(candles.index[-1], "hour"):
        _sig_ts = candles.index[-1]

    try:
        from datetime import timezone as _tz, timedelta as _td
        _IST = _tz(_td(hours=5, minutes=30))
        # Always store signal_time in IST — parquet/historical timestamps come in as UTC
        _sig_ts_ist = _sig_ts.astimezone(_IST) if hasattr(_sig_ts, "tzinfo") and _sig_ts.tzinfo is not None else _sig_ts
        _sig_time = str(_sig_ts_ist) if _sig_ts_ist is not None else None
        _hour = int(_sig_ts_ist.hour)
        _minute = int(_sig_ts_ist.minute)
    except (AttributeError, TypeError):
        _sig_time = str(_sig_ts) if _sig_ts is not None else None
        _hour = _minute = None

    # Real EOD PCR from NSE data (for analysis) — separate from mock OI used in strategy
    _real_pcr = None
    try:
        from app.market_data.real_oi import get_real_oi_data, oi_data_available
        from datetime import date as _date
        if oi_data_available() and _sig_ts is not None:
            _d = _sig_ts.date() if hasattr(_sig_ts, "date") else None
            if _d:
                _real_oi = get_real_oi_data(symbol, _d)
                if _real_oi and _real_oi.get("call_oi"):
                    _real_pcr = round(_real_oi["put_oi"] / _real_oi["call_oi"], 3)
    except Exception:
        pass

    signal_context = {
        "signal_time": _sig_time,
        "hour": _hour,
        "minute": _minute,
        "rsi": round(_rsi_val, 2),
        "vwap_distance_pct": _vwap_dist_pct,
        "atr": round(atr, 2),
        "pcr": _real_pcr,  # real NSE EOD PCR (live: from Upstox options chain via oi_data)
        "strategies_fired": [r.reason for r in strategy_results if r.fired],
    }
    entry = spot_price
    _sl_mult = sl_multiplier if sl_multiplier is not None else 1.0
    _tgt_mult = target_multiplier if target_multiplier is not None else 2.0
    if confidence.direction == "CALL":
        stop_loss = round(entry - atr * _sl_mult, 2)
        target = round(entry + atr * _tgt_mult, 2)
    else:
        stop_loss = round(entry + atr * _sl_mult, 2)
        target = round(entry - atr * _tgt_mult, 2)

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

    # AI filter — only for live signals, skip in backfill/mock to avoid API cost
    ai_verdict = "GO"
    ai_reason = ""
    if source == "live":
        from app.ai.signal_filter import evaluate_signal as _ai_eval
        _filter = await _ai_eval(symbol, confidence.direction, confidence.score, signal_context)
        ai_verdict = _filter.verdict
        ai_reason = _filter.reason
        signal_context["ai_verdict"] = ai_verdict
        signal_context["ai_reason"] = ai_reason
        if ai_verdict == "NO_GO":
            logger.info(
                "Signal blocked by AI filter",
                symbol=symbol,
                direction=confidence.direction,
                reason=ai_reason,
            )
            return None

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
        signal_context=signal_context,
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
