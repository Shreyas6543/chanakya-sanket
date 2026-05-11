import asyncio
import structlog
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.db.database import create_tables, AsyncSessionLocal
from app.db import models  # noqa: F401 — must import so SQLAlchemy registers all tables
from app.auth.upstox import get_login_url, exchange_code_for_token, save_token_to_env
from app.scheduler import create_scheduler, run_signal_engine, fetch_news_job
from app.market_data.websocket_client import ws_client
from app.market_data.mock import generate_mock_candles
from app.analytics.engine import get_overall_stats, get_reason_accuracy, get_regime_performance
from app.db.models import Signal, SignalState
from sqlalchemy import select

logger = structlog.get_logger()
settings = get_settings()
scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Chanakya Sanket", env=settings.env)
    await create_tables()
    logger.info("Database tables ready")

    if settings.upstox_access_token:
        logger.info("Live mode — starting Upstox WebSocket feed")
        asyncio.create_task(ws_client.connect())
    else:
        logger.info("Mock mode — seeding candle data")
        for symbol in ["NIFTY", "BANKNIFTY"]:
            generate_mock_candles(symbol, n=80)

    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    await ws_client.disconnect()
    logger.info("Shutting down Chanakya Sanket")


app = FastAPI(
    title="Chanakya Sanket — Trading Intelligence Engine",
    description="Explainable intraday options trading signal system. Edge through knowledge, not luck.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": settings.env,
        "mode": "mock" if not settings.upstox_access_token else "live",
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/auth/login")
async def upstox_login():
    url = get_login_url()
    return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;background:#0f0f0f;color:white;">
        <h2>Chanakya Sanket — Upstox Auth</h2>
        <p>Click below to authenticate with Upstox:</p>
        <a href="{url}" style="background:#6c2bd9;color:white;padding:12px 24px;border-radius:6px;
           text-decoration:none;font-size:16px;">Login with Upstox</a>
        </body></html>
    """)


@app.get("/auth/callback")
async def upstox_callback(code: str):
    try:
        token = await exchange_code_for_token(code)
        save_token_to_env(token)
        asyncio.create_task(ws_client.connect())
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;padding:40px;background:#0f0f0f;color:white;">
            <h2>Chanakya Sanket</h2>
            <p style="color:#4ade80;font-size:18px;">Connected to Upstox successfully.</p>
            <p>WebSocket feed starting. Signal engine is now switching to live data.</p>
            <p style="color:#aaa;font-size:14px;">Restart the server tomorrow morning to ensure clean startup in live mode.</p>
            </body></html>
        """)
    except Exception as e:
        logger.error("Token exchange failed", error=str(e))
        return HTMLResponse(f"""
            <html><body style="font-family:sans-serif;padding:40px;">
            <h2>Auth Failed</h2><p style="color:red;">{str(e)}</p>
            </body></html>
        """, status_code=400)


# ── Signals ───────────────────────────────────────────────────────────────────

@app.get("/signals")
async def list_signals(limit: int = 20, state: str = None):
    """List recent signals. Optionally filter by state: OPEN, TARGET_HIT, SL_HIT, EXPIRED"""
    async with AsyncSessionLocal() as session:
        query = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
        if state:
            query = query.where(Signal.state == state.upper())
        result = await session.execute(query)
        signals = result.scalars().all()
        return [
            {
                "id": s.id,
                "symbol": s.symbol,
                "direction": s.direction.value,
                "strike": s.strike,
                "expiry": s.expiry,
                "entry": s.entry,
                "sl": s.stop_loss,
                "target": s.target,
                "confidence": s.confidence,
                "reasons": s.reasons,
                "regime": s.regime.value,
                "state": s.state.value,
                "capital_required": s.capital_required,
                "created_at": s.created_at.isoformat(),
            }
            for s in signals
        ]


@app.get("/signals/open")
async def open_signals():
    """All currently open signals."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal).where(Signal.state == SignalState.OPEN)
        )
        signals = result.scalars().all()
        return {"count": len(signals), "signals": [
            {"id": s.id, "symbol": s.symbol, "direction": s.direction.value,
             "confidence": s.confidence, "entry": s.entry, "state": s.state.value}
            for s in signals
        ]}


# ── Daily Report ──────────────────────────────────────────────────────────────

@app.get("/signals/daily-report")
async def daily_report(date: str = None, include_mock: bool = False):
    """
    Daily signal report for a given date (YYYY-MM-DD). Defaults to today (IST).
    Only includes signals generated in live mode (upstox_access_token was set).
    """
    from datetime import date as date_type
    from app.utils.market_hours import now_ist
    from app.db.models import SignalOutcome

    if date:
        try:
            report_date = date_type.fromisoformat(date)
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
    else:
        report_date = now_ist().date()

    day_start = datetime.combine(report_date, datetime.min.time())
    day_end = datetime.combine(report_date, datetime.max.time())

    async with AsyncSessionLocal() as session:
        query = (
            select(Signal, SignalOutcome)
            .outerjoin(SignalOutcome, Signal.id == SignalOutcome.signal_id)
            .where(Signal.created_at >= day_start, Signal.created_at <= day_end)
            .order_by(Signal.created_at.asc())
        )
        if not include_mock:
            query = query.where(Signal.source.in_(["live", "historical"]))
        result = await session.execute(query)
        rows = result.all()

    if not rows:
        return {"date": str(report_date), "message": "No signals found for this date", "total": 0}

    signals_out = []
    wins = losses = open_count = expired = 0
    total_pnl = 0.0

    for signal, outcome in rows:
        state = signal.state.value
        pnl = round(outcome.pnl, 2) if outcome and outcome.pnl is not None else None
        result_label = outcome.result if outcome else None

        if state == "TARGET_HIT":
            wins += 1
        elif state == "SL_HIT":
            losses += 1
        elif state == "OPEN":
            open_count += 1
        elif state == "EXPIRED":
            expired += 1

        if pnl:
            total_pnl += pnl

        signals_out.append({
            "id": signal.id,
            "time": signal.created_at.strftime("%H:%M"),
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "entry": signal.entry,
            "sl": signal.stop_loss,
            "target": signal.target,
            "strike": signal.strike,
            "expiry": signal.expiry,
            "capital": signal.capital_required,
            "reasons": signal.reasons,
            "source": signal.source,
            "outcome": result_label or state,
            "pnl": pnl,
        })

    resolved = wins + losses
    return {
        "date": str(report_date),
        "total_signals": len(signals_out),
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "expired": expired,
        "win_rate": round(wins / resolved * 100, 1) if resolved > 0 else None,
        "total_pnl": round(total_pnl, 2),
        "signals": signals_out,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics")
async def analytics():
    async with AsyncSessionLocal() as session:
        return {
            "overall": await get_overall_stats(session),
            "by_reason": await get_reason_accuracy(session),
            "by_regime": await get_regime_performance(session),
        }


# ── Manual Triggers (for testing) ─────────────────────────────────────────────

@app.post("/trigger/signal-engine")
async def trigger_signal_engine(force: bool = False):
    """
    Manually trigger the signal engine.
    Use force=true to bypass market hours check (for testing).
    """
    from app.scheduler import _latest_news
    from app.market_data.mock import generate_mock_candles, get_mock_spot_price, get_mock_oi_data
    from app.market_data.candle_processor import get_candles
    from app.signals.generator import generate_signal
    from app.alerts.telegram import send_signal_alert
    from app.news.sentiment import get_symbol_sentiment

    await fetch_news_job()

    if not force:
        await run_signal_engine()
        return {"status": "triggered"}

    # Force mode — bypass market hours, use trending mock data
    results = []
    async with AsyncSessionLocal() as session:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            generate_mock_candles(symbol, n=80, trending=True)
            spot_price = get_mock_spot_price(symbol)
            oi_data = get_mock_oi_data(symbol, bullish=True)
            candles = get_candles(symbol, limit=100)
            sentiment = get_symbol_sentiment(symbol, _latest_news)

            signal = await generate_signal(
                symbol=symbol,
                candles=candles,
                spot_price=spot_price,
                oi_data=oi_data,
                sentiment_label=sentiment,
                session=session,
                force=True,
                source="mock",
            )
            if signal:
                await session.commit()
                await send_signal_alert(signal)
                results.append({"symbol": symbol, "confidence": signal.confidence,
                                 "direction": signal.direction.value, "signal_id": signal.id})

    return {"status": "triggered", "mode": "force", "signals_generated": results}


@app.get("/debug/strategies/{symbol}")
async def debug_strategies(symbol: str = "NIFTY"):
    """Show what each strategy returns for current candle data."""
    from app.market_data.mock import generate_mock_candles, get_mock_oi_data
    from app.market_data.candle_processor import get_candles
    from app.strategies.vwap_breakout import VWAPBreakoutStrategy
    from app.strategies.rsi_momentum import RSIMomentumStrategy
    from app.strategies.bullish_engulfing import BullishEngulfingStrategy
    from app.strategies.opening_range import OpeningRangeBreakoutStrategy
    from app.strategies.oi_buildup import OIBuildupStrategy
    from app.signals.confidence import calculate_confidence
    from app.utils.regime import detect_regime
    from app.indicators.rsi import calculate_rsi
    from app.indicators.vwap import calculate_vwap

    generate_mock_candles(symbol, n=80, trending=True)
    candles = get_candles(symbol, limit=100)
    oi_data = get_mock_oi_data(symbol, bullish=True)

    strategies = [
        VWAPBreakoutStrategy(),
        RSIMomentumStrategy(),
        BullishEngulfingStrategy(),
        OpeningRangeBreakoutStrategy(),
        OIBuildupStrategy(),
    ]

    results = []
    strategy_signals = []
    for s in strategies:
        sig = s.evaluate(candles, oi_data)
        strategy_signals.append(sig)
        results.append({"strategy": s.name, "fired": sig.fired, "direction": sig.direction, "points": sig.points, "details": sig.details})

    confidence = calculate_confidence(strategy_signals)
    regime = detect_regime(candles)
    rsi = calculate_rsi(candles["close"])
    vwap = calculate_vwap(candles)

    return {
        "symbol": symbol,
        "candle_count": len(candles),
        "regime": regime,
        "rsi_last": round(float(rsi.iloc[-1]), 2) if not rsi.empty else None,
        "rsi_prev": round(float(rsi.iloc[-2]), 2) if len(rsi) > 1 else None,
        "last_close": round(float(candles["close"].iloc[-1]), 2),
        "vwap_last": round(float(vwap.iloc[-1]), 2),
        "strategies": results,
        "confidence": {"score": confidence.score, "direction": confidence.direction, "reasons": confidence.reasons},
        "min_required": settings.min_confidence_score,
        "would_generate_signal": confidence.score >= settings.min_confidence_score,
    }


@app.post("/trigger/evaluate-signals")
async def trigger_evaluate_signals(ticks: int = 1):
    """
    Manually run the signal evaluator.
    ticks: how many 1-minute price ticks to simulate (use 30-60 to fast-forward to resolution).
    """
    from app.signals.lifecycle import evaluate_signal_tick
    from app.market_data.mock import get_mock_spot_price
    from app.db.models import Signal, SignalState
    from sqlalchemy import select

    resolved = []
    async with AsyncSessionLocal() as session:
        for _ in range(ticks):
            result = await session.execute(
                select(Signal).where(Signal.state == SignalState.OPEN)
            )
            open_signals = result.scalars().all()
            if not open_signals:
                break

            for signal in open_signals:
                current_price = get_mock_spot_price(signal.symbol)
                new_state = await evaluate_signal_tick(signal, current_price, session)
                if new_state:
                    resolved.append({
                        "signal_id": signal.id,
                        "symbol": signal.symbol,
                        "direction": signal.direction.value,
                        "new_state": new_state,
                        "exit_price": current_price,
                    })

        await session.commit()

    # Send Telegram alert for each resolved signal
    from app.alerts.telegram import send_text_alert
    for r in resolved:
        emoji = "TARGET HIT" if r["new_state"] == "TARGET_HIT" else "SL HIT"
        await send_text_alert(
            f"*{r['symbol']} Signal #{r['signal_id']} — {emoji}*\n"
            f"Direction: {r['direction']} | Exit: {r['exit_price']:.2f}"
        )

    return {"ticks_simulated": ticks, "resolved": resolved}


@app.post("/trigger/simulate")
async def trigger_simulate(date: str = None, count: int = 10):
    """
    Replay a real trading day using Upstox historical candles.
    Slides through the day's 5m candles, runs the signal engine at each window,
    stops after generating `count` signals. Signals tagged source='historical'.

    date: YYYY-MM-DD (defaults to today)
    count: max signals to generate (default 10)
    """
    from datetime import date as date_type
    from app.market_data.historical import fetch_historical_candles
    from app.signals.generator import generate_signal
    from app.signals.strike_selector import select_expiry
    from app.market_data.mock import get_mock_oi_data
    from app.alerts.telegram import send_signal_alert
    from app.utils.market_hours import now_ist
    from app.news.sentiment import get_symbol_sentiment
    from app.scheduler import _latest_news

    if date:
        try:
            sim_date = date_type.fromisoformat(date)
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
    else:
        sim_date = now_ist().date()

    if not settings.upstox_access_token:
        return {"error": "Live mode required. Set UPSTOX_ACCESS_TOKEN in .env"}

    results = []
    MIN_CANDLES = 50  # minimum window needed for indicators

    async with AsyncSessionLocal() as session:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            if len(results) >= count:
                break

            candles_full = await fetch_historical_candles(symbol, sim_date)
            if candles_full.empty or len(candles_full) < MIN_CANDLES:
                continue

            # Slide through the day: try each window from MIN_CANDLES to end
            for window_end in range(MIN_CANDLES, len(candles_full) + 1):
                if len(results) >= count:
                    break

                window = candles_full.iloc[:window_end].copy()
                spot_price = float(window["close"].iloc[-1])
                # Align mock OI direction with price action to avoid direction conflicts.
                # When price is above VWAP → bullish OI; below VWAP → bearish OI.
                from app.indicators.vwap import calculate_vwap as _calc_vwap
                _vwap_val = float(_calc_vwap(window).iloc[-1])
                _bullish = spot_price >= _vwap_val
                oi_data = get_mock_oi_data(symbol, bullish=_bullish)
                sentiment = get_symbol_sentiment(symbol, _latest_news)
                expiry = select_expiry(symbol, reference_date=sim_date)

                signal = await generate_signal(
                    symbol=symbol,
                    candles=window,
                    spot_price=spot_price,
                    oi_data=oi_data,
                    sentiment_label=sentiment,
                    session=session,
                    force=True,
                    source="historical",
                )

                if signal:
                    await session.commit()
                    await send_signal_alert(signal)
                    results.append({
                        "symbol": signal.symbol,
                        "direction": signal.direction.value,
                        "confidence": signal.confidence,
                        "entry": signal.entry,
                        "strike": signal.strike,
                        "signal_id": signal.id,
                        "candle_time": str(window["timestamp"].iloc[-1]),
                    })

    return {
        "date": str(sim_date),
        "signals_generated": len(results),
        "requested": count,
        "signals": results,
    }


@app.post("/trigger/test-signal")
async def trigger_test_signal():
    """Send a fake test signal to Telegram to verify the full alert pipeline."""
    from app.db.models import Signal, SignalDirection, MarketRegime, SignalState
    from app.alerts.telegram import send_signal_alert
    from datetime import datetime

    async with AsyncSessionLocal() as session:
        # Realistic test signal — capital sizing respects 10% cap
        # Estimated ATM NIFTY premium ~₹150, lot size 25
        estimated_premium = 150.0
        lot_size = 25
        lots_by_capital = max(1, int(settings.max_capital_per_trade / (estimated_premium * lot_size)))
        lots_by_risk = max(1, int(settings.risk_amount / (estimated_premium * 0.5 * lot_size)))
        suggested_lots = min(lots_by_capital, lots_by_risk)
        capital_required = round(estimated_premium * suggested_lots * lot_size, 2)

        signal = Signal(
            symbol="NIFTY",
            direction=SignalDirection.CALL,
            strike=24550.0,
            expiry="2026-05-15",
            entry=24500.0,
            stop_loss=24350.0,
            target=24800.0,
            confidence=78,
            reasons={
                "vwap_breakout": 20,
                "rsi_momentum": 15,
                "oi_buildup": 25,
                "positive_sentiment": 10,
            },
            regime=MarketRegime.TRENDING,
            capital_required=capital_required,
            suggested_lots=suggested_lots,
            state=SignalState.OPEN,
            created_at=datetime.utcnow(),
        )
        session.add(signal)
        await session.flush()
        await send_signal_alert(signal)
        await session.commit()

    return {"status": "test signal sent", "signal_id": signal.id, "check": "your Telegram"}
