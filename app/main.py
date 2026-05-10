import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.db.database import create_tables, AsyncSessionLocal
from app.db import models  # noqa: F401 — must import so SQLAlchemy registers all tables
from app.auth.upstox import get_login_url, exchange_code_for_token, save_token_to_env
from app.scheduler import create_scheduler, run_signal_engine, fetch_news_job
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

    # Seed mock candles on startup if no live data
    if not settings.upstox_access_token:
        logger.info("Mock mode — seeding candle data")
        for symbol in ["NIFTY", "BANKNIFTY"]:
            generate_mock_candles(symbol, n=80)

    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
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
        return HTMLResponse("""
            <html><body style="font-family:sans-serif;padding:40px;background:#0f0f0f;color:white;">
            <h2>Chanakya Sanket</h2>
            <p style="color:#4ade80;font-size:18px;">Connected to Upstox successfully.</p>
            <p>You can close this tab. Signal engine is now running on live data.</p>
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
