import asyncio
import structlog
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.db.database import create_tables, AsyncSessionLocal
from app.db import models  # noqa: F401 — must import so SQLAlchemy registers all tables
from app.auth.upstox import get_login_url, exchange_code_for_token, save_token_to_env
from app.scheduler import create_scheduler, run_signal_engine, fetch_news_job
from app.market_data.websocket_client import ws_client
from app.market_data.mock import generate_mock_candles
from app.analytics.engine import get_overall_stats, get_reason_accuracy, get_regime_performance, get_time_of_day_performance, get_strategy_combo_performance
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

    # Startup token check — alert immediately if token is missing on a weekday
    from app.auth.upstox import validate_token
    from app.utils.market_hours import now_ist as _now_ist
    from app.alerts.telegram import send_text_alert as _alert
    _now = _now_ist()
    if _now.weekday() < 5:  # Mon–Fri only
        _valid = await validate_token()
        if not _valid:
            logger.warning("Startup: Upstox token missing or expired")
            asyncio.create_task(_alert(
                "*⚠️ Chanakya Sanket Started — No Valid Token*\n\n"
                "Running in mock mode\\.\n"
                "To switch to live: `http://localhost:8000/auth/login`"
            ))

    if settings.upstox_access_token:
        logger.info("Live mode — seeding candles")
        from app.market_data.historical import fetch_historical_candles
        from app.market_data.candle_processor import seed_candles
        from app.utils.market_hours import now_ist
        from app.db.models import Candle as CandleModel
        from sqlalchemy import select as sa_select
        from datetime import timedelta, timezone, time as dt_time
        import pandas as pd
        today = now_ist().date()
        today_start = datetime.combine(today, dt_time.min).replace(tzinfo=timezone.utc)
        for symbol in ["NIFTY", "BANKNIFTY"]:
            all_candles = []

            # 1. Load today's intraday candles from DB — survives mid-session restarts
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    sa_select(CandleModel)
                    .where(
                        CandleModel.symbol == symbol,
                        CandleModel.timeframe == "5m",
                        CandleModel.timestamp >= today_start,
                    )
                    .order_by(CandleModel.timestamp)
                )
                db_candles = result.scalars().all()
            if db_candles:
                df_today = pd.DataFrame([{
                    "timestamp": c.timestamp, "open": c.open, "high": c.high,
                    "low": c.low, "close": c.close, "volume": c.volume,
                } for c in db_candles])
                all_candles.append(df_today)
                logger.info("Loaded today's candles from DB", symbol=symbol, count=len(db_candles))

            # 2. Previous trading days from Upstox API for indicator history (RSI, EMA, ATR)
            for days_back in [3, 2, 1]:
                d = today - timedelta(days=days_back)
                if d.weekday() >= 5:  # skip weekends
                    continue
                df = await fetch_historical_candles(symbol, d)
                if not df.empty:
                    all_candles.append(df)

            # 3. If no DB candles for today, fall back to Upstox intraday API
            if not db_candles:
                df_today_api = await fetch_historical_candles(symbol, today)
                if not df_today_api.empty:
                    all_candles.append(df_today_api)

            if all_candles:
                combined = pd.concat(all_candles, ignore_index=True)
                combined = (combined.sort_values("timestamp")
                            .drop_duplicates(subset=["timestamp"])
                            .reset_index(drop=True))
                seed_candles(symbol, combined)
            else:
                logger.warning("No historical candles found — buffer empty", symbol=symbol)
        logger.info("Starting Upstox WebSocket feed")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": settings.env,
        "mode": "mock" if not settings.upstox_access_token else "live",
    }


@app.get("/debug/live-prices")
@app.get("/api/debug/live-prices")
async def debug_live_prices():
    from app.market_data.websocket_client import LIVE_PRICES
    return {"live_prices": LIVE_PRICES}


@app.get("/debug/real-strategies/{symbol}")
async def debug_real_strategies(symbol: str = "NIFTY"):
    """Evaluate strategies on real candle data (not mock)."""
    from app.market_data.candle_processor import get_candles
    from app.market_data.websocket_client import get_live_price
    from app.strategies.vwap_breakout import VWAPBreakoutStrategy
    from app.strategies.rsi_momentum import RSIMomentumStrategy
    from app.strategies.opening_range import OpeningRangeBreakoutStrategy
    from app.signals.confidence import calculate_confidence
    from app.utils.regime import detect_regime
    from app.indicators.rsi import calculate_rsi
    from app.indicators.vwap import calculate_vwap

    candles = get_candles(symbol, limit=100)
    if len(candles) < 20:
        return {"symbol": symbol, "candle_count": len(candles), "error": "Insufficient candles"}

    regime = detect_regime(candles)
    rsi = calculate_rsi(candles["close"])
    vwap = calculate_vwap(candles)
    last_close = float(candles["close"].iloc[-1])
    last_vwap = float(vwap.iloc[-1])

    strategies = [VWAPBreakoutStrategy(), RSIMomentumStrategy(), OpeningRangeBreakoutStrategy()]
    strategy_signals = []
    results = []
    for s in strategies:
        sig = s.evaluate(candles)
        strategy_signals.append(sig)
        results.append({"strategy": s.name, "fired": sig.fired, "direction": sig.direction,
                        "points": sig.points, "details": sig.details})

    confidence = calculate_confidence(strategy_signals)
    return {
        "symbol": symbol,
        "candle_count": len(candles),
        "spot_price": get_live_price(symbol),
        "last_close": round(last_close, 2),
        "last_vwap": round(last_vwap, 2),
        "vwap_diff_pct": round((last_close - last_vwap) / last_vwap * 100, 3),
        "rsi_last": round(float(rsi.iloc[-1]), 2) if not rsi.empty else None,
        "rsi_prev": round(float(rsi.iloc[-2]), 2) if len(rsi) > 1 else None,
        "regime": regime,
        "strategies": results,
        "confidence": {"score": confidence.score, "direction": confidence.direction, "reasons": confidence.reasons},
        "min_required": settings.min_confidence_score,
        "would_fire": confidence.score >= settings.min_confidence_score,
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
            <p style="color:#aaa;font-size:14px;">Token saved. WebSocket feed is starting. You can close this tab.</p>
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
        elif state == "USER_CLOSED":
            expired += 1  # Treat same as expired for reporting

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

    # EXPIRED / USER_CLOSED = real losses (theta decay + forced exit). Include in denominator.
    resolved = wins + losses + expired
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
            "by_hour": await get_time_of_day_performance(session),
            "by_strategy_combo": await get_strategy_combo_performance(session),
        }


# ── Dashboard API ─────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
async def api_dashboard(
    start_date: str | None = None,
    end_date: str | None = None,
    strategies: str | None = None,  # comma-separated: "vwap_breakout,rsi_momentum"
):
    """
    Filtered analytics for the UI dashboard.
    Returns overview stats + signal list filtered by date range and strategies fired.
    strategies='' or omitted → all signals. Otherwise only signals where ANY of those strategies fired.
    """
    from datetime import date as date_type, datetime, timezone, timedelta
    from app.db.models import SignalOutcome, StrategyResult
    from sqlalchemy import and_, text as sa_text

    strategy_list = [s.strip() for s in strategies.split(",")] if strategies else []

    IST = timezone(timedelta(hours=5, minutes=30))

    async with AsyncSessionLocal() as session:
        # Base query: signals joined with outcomes
        q = (
            select(Signal, SignalOutcome)
            .outerjoin(SignalOutcome, Signal.id == SignalOutcome.signal_id)
        )

        # Date filter on signal_context->>'signal_time' (the actual trading date),
        # NOT created_at (which reflects when the backfill script ran — always today).
        # Pass datetime objects (not strings) so asyncpg sends TIMESTAMPTZ, not VARCHAR.
        if start_date:
            try:
                d_start = datetime.fromisoformat(f"{start_date}T00:00:00").replace(tzinfo=IST)
            except ValueError:
                return {"error": f"Invalid start_date: {start_date}"}
            q = q.where(
                sa_text("(signal_context->>'signal_time')::timestamptz >= :start")
                .bindparams(start=d_start)
            )
        if end_date:
            try:
                d_end = datetime.fromisoformat(f"{end_date}T23:59:59").replace(tzinfo=IST)
            except ValueError:
                return {"error": f"Invalid end_date: {end_date}"}
            q = q.where(
                sa_text("(signal_context->>'signal_time')::timestamptz <= :end")
                .bindparams(end=d_end)
            )

        # Strategy filter: only signals where at least one selected strategy fired
        if strategy_list:
            subq = (
                select(StrategyResult.signal_id)
                .where(
                    and_(
                        StrategyResult.fired == True,
                        StrategyResult.strategy_name.in_(strategy_list),
                    )
                )
                .distinct()
            )
            q = q.where(Signal.id.in_(subq))

        q = q.order_by(Signal.created_at.desc())
        result = await session.execute(q)
        rows = result.all()

    # Aggregate overview
    total = wins = losses = expired = 0
    total_pnl = 0.0
    by_symbol: dict[str, dict] = {}
    by_direction: dict[str, dict] = {}
    signals_out = []

    for signal, outcome in rows:
        state = signal.state.value
        result_label = outcome.result if outcome else None
        pnl = round(outcome.pnl, 2) if outcome and outcome.pnl is not None else None

        total += 1
        if result_label == "TARGET_HIT":
            wins += 1
        elif result_label == "SL_HIT":
            losses += 1
        elif state in ("EXPIRED", "USER_CLOSED"):
            expired += 1
        if pnl:
            total_pnl += pnl

        # by symbol
        sym = signal.symbol
        if sym not in by_symbol:
            by_symbol[sym] = {"total": 0, "wins": 0, "pnl": 0.0}
        by_symbol[sym]["total"] += 1
        if result_label == "TARGET_HIT":
            by_symbol[sym]["wins"] += 1
        if pnl:
            by_symbol[sym]["pnl"] += pnl

        # by direction
        d = signal.direction.value
        if d not in by_direction:
            by_direction[d] = {"total": 0, "wins": 0}
        by_direction[d]["total"] += 1
        if result_label == "TARGET_HIT":
            by_direction[d]["wins"] += 1

        ctx = signal.signal_context or {}
        # Use signal_time from context (actual trading date) — created_at is backfill run date
        signal_time = ctx.get("signal_time") or signal.created_at.isoformat()
        signals_out.append({
            "id": signal.id,
            "signal_time": signal_time,
            "created_at": signal.created_at.isoformat(),
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "strike": signal.strike,
            "expiry": signal.expiry,
            "entry": signal.entry,
            "sl": signal.stop_loss,
            "target": signal.target,
            "regime": signal.regime.value,
            "source": signal.source,
            "state": state,
            "outcome": result_label or state,
            "pnl": pnl,
            "strategies_fired": ctx.get("strategies_fired", []),
            "rsi": ctx.get("rsi"),
            "vwap_distance_pct": ctx.get("vwap_distance_pct"),
            "hour": ctx.get("hour"),
        })

    # EXPIRED / USER_CLOSED = real losses (theta decay). Include in WR denominator.
    resolved = wins + losses + expired
    overview = {
        "total_signals": total,
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "open": total - wins - losses - expired,
        "win_rate": round(wins / resolved * 100, 1) if resolved > 0 else 0,
        "total_pnl": round(total_pnl, 2),
    }

    by_symbol_out = [
        {
            "symbol": k,
            "total": v["total"],
            "wins": v["wins"],
            "win_rate": round(v["wins"] / v["total"] * 100, 1) if v["total"] else 0,
            "pnl": round(v["pnl"], 2),
        }
        for k, v in by_symbol.items()
    ]
    by_direction_out = [
        {
            "direction": k,
            "total": v["total"],
            "wins": v["wins"],
            "win_rate": round(v["wins"] / v["total"] * 100, 1) if v["total"] else 0,
        }
        for k, v in by_direction.items()
    ]

    return {
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "strategies": strategy_list or "all",
        },
        "overview": overview,
        "by_symbol": by_symbol_out,
        "by_direction": by_direction_out,
        "signals": signals_out,
    }


# ── Signal Actions ────────────────────────────────────────────────────────────

@app.post("/signals/{signal_id}/mark-sold")
async def mark_signal_sold(signal_id: int):
    """Mark an OPEN signal as USER_CLOSED (user manually squared off)."""
    from app.db.models import SignalOutcome
    from app.utils.market_hours import now_ist

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()

        if not signal:
            return {"error": f"Signal {signal_id} not found"}
        if signal.state != SignalState.OPEN:
            return {"error": f"Signal is already {signal.state.value} — cannot mark sold"}

        signal.state = SignalState.USER_CLOSED
        signal.evaluated_at = now_ist()
        outcome = SignalOutcome(
            signal_id=signal.id,
            result="USER_CLOSED",
            pnl=None,
            evaluated_at=now_ist(),
        )
        session.add(outcome)
        await session.commit()

    return {"ok": True, "signal_id": signal_id, "state": "USER_CLOSED"}


# ── Claude AI Analyst ─────────────────────────────────────────────────────────

@app.post("/api/ai/analyze")
async def ai_analyze(body: dict):
    """
    Stream a Claude analysis of the current dashboard data.
    Body: { question: str, context: { overview, by_symbol, by_direction, signals, filters } }
    Returns: text/event-stream — each event is a text chunk, ends with [DONE].
    """
    from app.ai.claude_analyst import stream_analysis

    question = (body.get("question") or "").strip()
    context = body.get("context") or {}

    if not question:
        async def empty():
            yield "data: Please enter a question.\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    async def generator():
        try:
            async for chunk in stream_analysis(question, context):
                # SSE format: escape newlines inside a data field
                escaped = chunk.replace("\n", "\ndata: ")
                yield f"data: {escaped}\n\n"
        except Exception as e:
            yield f"data: Error: {e}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/oi")
async def admin_oi_status():
    """Current OI strategy toggle status + snapshot count."""
    from app.utils.oi_toggle import is_oi_enabled
    from app.market_data.real_oi import oi_coverage_stats
    from app.db.models import MarketSnapshot
    from sqlalchemy import func
    enabled = await is_oi_enabled()
    async with AsyncSessionLocal() as session:
        r = await session.execute(select(func.count()).select_from(MarketSnapshot))
        snapshot_count = r.scalar()
    return {
        "oi_strategy_enabled": enabled,
        "note": "ON = NSE Bhavcopy OI used in backfill; live Upstox OI used in live mode. OFF = OI skipped (price action only).",
        "nse_bhavcopy_days": oi_coverage_stats(),
        "intraday_snapshots_stored": snapshot_count,
    }


@app.post("/admin/oi/enable")
async def admin_oi_enable():
    from app.utils.oi_toggle import set_oi_enabled
    await set_oi_enabled(True)
    return {"oi_strategy_enabled": True, "message": "OI strategy enabled. Backfill will use NSE Bhavcopy OI. Live mode uses Upstox options chain."}


@app.post("/admin/oi/disable")
async def admin_oi_disable():
    from app.utils.oi_toggle import set_oi_enabled
    await set_oi_enabled(False)
    return {"oi_strategy_enabled": False, "message": "OI strategy disabled. Price action only (VWAP + RSI + ORB)."}


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


async def _simulate_one_day(
    sim_date, session, count: int = 10, notify: bool = True,
    min_confidence: int | None = None,
    points_vwap: int | None = None,
    points_rsi: int | None = None,
    points_oi: int | None = None,
    points_orb: int | None = None,
    target_multiplier: float | None = None,
    sl_multiplier: float | None = None,
):
    """
    Core simulate logic for a single trading date.
    Slides through 5m candles, runs strategies, evaluates outcomes against rest of day.
    Returns list of signal result dicts. notify=False suppresses Telegram alerts.
    """
    from app.market_data.historical import fetch_historical_candles
    from app.signals.generator import generate_signal
    from app.signals.strike_selector import select_expiry
    from app.alerts.telegram import send_signal_alert
    from app.news.sentiment import get_symbol_sentiment
    from app.signals.lifecycle import _close_signal
    from app.db.models import SignalState
    from app.indicators.vwap import calculate_vwap as _calc_vwap
    from app.scheduler import _latest_news

    results = []
    MIN_CANDLES = 50
    MAX_DAILY_LOSSES = 3  # Mirror of scheduler.py circuit breaker
    daily_sl_count = 0    # Global SL counter across both symbols for this day

    # Find the previous trading day to use as seed candles (mirrors live server startup)
    from datetime import timedelta
    prev_date = sim_date - timedelta(days=1)
    while prev_date.weekday() >= 5:
        prev_date -= timedelta(days=1)

    for symbol in ["NIFTY", "BANKNIFTY"]:
        if len(results) >= count:
            break
        if daily_sl_count >= MAX_DAILY_LOSSES:
            break  # Circuit breaker: wipeout day — stop all symbols

        candles_today = await fetch_historical_candles(symbol, sim_date)
        if candles_today.empty:
            continue

        # Seed with previous day's candles so strategies have history from candle 1
        candles_prev = await fetch_historical_candles(symbol, prev_date)
        if not candles_prev.empty:
            import pandas as pd
            candles_full = pd.concat([candles_prev.tail(MIN_CANDLES), candles_today], ignore_index=True)
        else:
            candles_full = candles_today

        if len(candles_full) < MIN_CANDLES:
            continue

        # Slide window starting from the first candle of today (seed already provides history)
        today_start_idx = len(candles_full) - len(candles_today)
        for window_end in range(today_start_idx + 1, len(candles_full) + 1):
            if len(results) >= count:
                break
            if daily_sl_count >= MAX_DAILY_LOSSES:
                break  # Circuit breaker tripped mid-symbol

            window = candles_full.iloc[:window_end].copy()
            spot_price = float(window["close"].iloc[-1])
            _vwap_val = float(_calc_vwap(window).iloc[-1])
            # OI in backfill uses NSE Bhavcopy EOD data (real_oi.py).
            # Toggled on/off via /admin/oi — default OFF since EOD OI has wrong granularity.
            from app.utils.oi_toggle import is_oi_enabled
            from app.market_data.real_oi import get_real_oi_data
            oi_data = get_real_oi_data(symbol, sim_date) if await is_oi_enabled() else None
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
                min_confidence=min_confidence,
                points_vwap=points_vwap,
                points_rsi=points_rsi,
                points_oi=points_oi,
                points_orb=points_orb,
                target_multiplier=target_multiplier,
                sl_multiplier=sl_multiplier,
            )

            if signal:
                await session.commit()
                if notify:
                    await send_signal_alert(signal)

                # Evaluate against remaining candles of the day
                outcome_state = "EXPIRED"
                outcome_price = None
                outcome_candle = None
                for fc in candles_full.iloc[window_end:].itertuples():
                    close = float(fc.close)
                    if signal.direction.value == "CALL":
                        if close >= signal.target:
                            outcome_state, outcome_price, outcome_candle = "TARGET_HIT", close, str(fc.timestamp)
                            break
                        elif close <= signal.stop_loss:
                            outcome_state, outcome_price, outcome_candle = "SL_HIT", close, str(fc.timestamp)
                            break
                    else:
                        if close <= signal.target:
                            outcome_state, outcome_price, outcome_candle = "TARGET_HIT", close, str(fc.timestamp)
                            break
                        elif close >= signal.stop_loss:
                            outcome_state, outcome_price, outcome_candle = "SL_HIT", close, str(fc.timestamp)
                            break

                if outcome_state == "SL_HIT":
                    daily_sl_count += 1

                await _close_signal(signal, SignalState(outcome_state), outcome_price, session)
                await session.commit()

                results.append({
                    "symbol": signal.symbol,
                    "direction": signal.direction.value,
                    "confidence": signal.confidence,
                    "entry": signal.entry,
                    "strike": signal.strike,
                    "sl": signal.stop_loss,
                    "target": signal.target,
                    "signal_id": signal.id,
                    "signal_time": str(window["timestamp"].iloc[-1]),
                    "outcome": outcome_state,
                    "outcome_price": outcome_price,
                    "outcome_time": outcome_candle,
                })

    return results


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
    from app.utils.market_hours import now_ist

    if date:
        try:
            sim_date = date_type.fromisoformat(date)
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
    else:
        sim_date = now_ist().date()

    if not settings.upstox_access_token:
        return {"error": "Live mode required. Set UPSTOX_ACCESS_TOKEN in .env"}

    async with AsyncSessionLocal() as session:
        results = await _simulate_one_day(sim_date, session, count=count, notify=True)

    return {
        "date": str(sim_date),
        "signals_generated": len(results),
        "requested": count,
        "signals": results,
    }


@app.post("/trigger/backfill")
async def trigger_backfill(
    weeks: int = 6,
    signals_per_day: int = 10,
    min_confidence: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    points_vwap: int | None = None,
    points_rsi: int | None = None,
    points_oi: int | None = None,
    points_orb: int | None = None,
    target_multiplier: float | None = None,
    sl_multiplier: float | None = None,
):
    """
    Replay real trading days to build historical signal data.
    Runs simulate on every trading day, evaluates outcomes, saves to DB.
    Sends ONE Telegram summary at the end (no per-signal alerts).

    weeks: how many weeks back from today (default 6, ignored if start_date given)
    start_date / end_date: explicit YYYY-MM-DD range (overrides weeks)
    signals_per_day: max signals per day per run (default 5)
    min_confidence: override confidence threshold for this run (default: uses .env)
    """
    from datetime import date as date_type, timedelta
    from app.utils.market_hours import now_ist
    from app.alerts.telegram import send_text_alert

    if not settings.upstox_access_token:
        return {"error": "Live mode required. Set UPSTOX_ACCESS_TOKEN in .env"}

    today = now_ist().date()

    if start_date:
        range_start = date_type.fromisoformat(start_date)
        range_end = date_type.fromisoformat(end_date) if end_date else today
    else:
        range_start = today - timedelta(weeks=weeks)
        range_end = today

    # Build list of weekdays (Mon-Fri) in range — weekends and holidays auto-skipped
    # (Upstox returns empty data for holidays, _simulate_one_day handles gracefully)
    all_dates = []
    d = range_start
    while d < range_end:
        if d.weekday() < 5:  # Mon=0 … Fri=4
            all_dates.append(d)
        d += timedelta(days=1)

    logger.info("Starting backfill", start=str(range_start), end=str(range_end), trading_days=len(all_dates))

    day_results = []
    total_signals = total_wins = total_losses = total_expired = 0

    async with AsyncSessionLocal() as session:
        for sim_date in all_dates:
            signals = await _simulate_one_day(
                sim_date, session, count=signals_per_day, notify=False,
                min_confidence=min_confidence,
                points_vwap=points_vwap, points_rsi=points_rsi,
                points_oi=points_oi, points_orb=points_orb,
                target_multiplier=target_multiplier,
                sl_multiplier=sl_multiplier,
            )
            wins = sum(1 for s in signals if s["outcome"] == "TARGET_HIT")
            losses = sum(1 for s in signals if s["outcome"] == "SL_HIT")
            expired = sum(1 for s in signals if s["outcome"] == "EXPIRED")
            total_signals += len(signals)
            total_wins += wins
            total_losses += losses
            total_expired += expired
            if signals:
                day_results.append({
                    "date": str(sim_date),
                    "signals": len(signals),
                    "wins": wins,
                    "losses": losses,
                    "expired": expired,
                })
            logger.info("Backfill day done", date=str(sim_date), signals=len(signals), wins=wins, losses=losses)

    resolved = total_wins + total_losses + total_expired  # EXPIRED = real cost (theta decay)
    win_rate = round(total_wins / resolved * 100, 1) if resolved > 0 else None

    # Send one Telegram summary
    summary_lines = "\n".join(
        f"  {r['date']}: {r['signals']} signals  ✅{r['wins']} ❌{r['losses']} ⏳{r['expired']}"
        for r in day_results
    )
    await send_text_alert(
        f"📊 *Backfill Complete — {weeks} weeks*\n\n"
        f"📅 Trading days processed: {len(all_dates)}\n"
        f"🔖 Total signals: {total_signals}\n"
        f"✅ Target hit: {total_wins}\n"
        f"❌ SL hit: {total_losses}\n"
        f"⏳ Expired: {total_expired}\n"
        f"🎯 Win rate: *{win_rate}%*\n\n"
        f"_Run `make analytics` for full breakdown_"
    )

    return {
        "weeks": weeks,
        "trading_days_checked": len(all_dates),
        "trading_days_with_signals": len(day_results),
        "total_signals": total_signals,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_expired": total_expired,
        "win_rate": win_rate,
        "by_day": day_results,
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
