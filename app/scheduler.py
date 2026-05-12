"""
Chanakya Sanket — Main Scheduler
Orchestrates the full signal engine pipeline during market hours.
"""
import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.db.database import AsyncSessionLocal
from app.market_data.candle_processor import get_candles, clear_candles
from app.market_data.mock import generate_mock_candles, get_mock_spot_price, get_mock_oi_data
from app.news.fetcher import fetch_news
from app.news.sentiment import get_symbol_sentiment
from app.signals.generator import generate_signal
from app.signals.lifecycle import expire_eod_signals, get_open_signal_count
from app.alerts.telegram import send_signal_alert, send_text_alert
from app.analytics.engine import get_overall_stats
from app.utils.market_hours import is_market_open, can_generate_signals
from app.utils.oi_toggle import is_oi_enabled
from app.db.models import Signal, SignalState, MarketRegime, MarketSnapshot
from sqlalchemy import select

logger = structlog.get_logger()
settings = get_settings()

# Track if we're using mock data
USE_MOCK = not bool(settings.upstox_access_token)

# Cache latest news articles
_latest_news: list[dict] = []

# Consecutive SL hits per symbol today — reset at 9:15 AM
# If a symbol hits 2 consecutive SL_HITs, skip it for the rest of the day.
# Backtested: raises win rate from 34.4% → 37.7% across 6 weeks of data.
_consecutive_losses: dict[str, int] = {"NIFTY": 0, "BANKNIFTY": 0}
MAX_CONSECUTIVE_LOSSES = 2

# Global daily circuit breaker — if total SL hits across ALL symbols >= this,
# stop all signal generation for the rest of the day.
# Prevents wipeout days (e.g. 5 losses on Apr 10, 15, 28, 30 in backtest).
_daily_losses_total: int = 0
MAX_DAILY_LOSSES = 3


async def run_signal_engine():
    """
    Core job — runs every 5 minutes during market hours.
    For each symbol: fetch candles → check regime → run strategies → generate signal → alert.
    """
    if not can_generate_signals():
        logger.debug("Outside signal generation window — skipping")
        return

    if _daily_losses_total >= MAX_DAILY_LOSSES:
        logger.info("Signal engine paused — daily loss circuit breaker active",
                    daily_losses=_daily_losses_total)
        return

    logger.info("Signal engine running", mock=USE_MOCK)

    async with AsyncSessionLocal() as session:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                if _consecutive_losses[symbol] >= MAX_CONSECUTIVE_LOSSES:
                    logger.info("Signal skipped — consecutive loss gate active", symbol=symbol,
                                consecutive_losses=_consecutive_losses[symbol])
                    continue

                oi_enabled = await is_oi_enabled()
                if USE_MOCK:
                    generate_mock_candles(symbol, n=5)  # Add 5 new mock candles
                    spot_price = get_mock_spot_price(symbol)
                    oi_data = get_mock_oi_data(symbol) if oi_enabled else None
                else:
                    from app.market_data.websocket_client import get_live_price
                    from app.market_data.options_chain import fetch_options_chain
                    from app.signals.strike_selector import select_expiry
                    spot_price = get_live_price(symbol)
                    if not spot_price:
                        logger.warning("No live price yet — WebSocket not ready", symbol=symbol)
                        continue
                    expiry = select_expiry(symbol)
                    oi_data = await fetch_options_chain(symbol, expiry) if oi_enabled else None

                candles = get_candles(symbol, limit=100)
                if len(candles) < 20:
                    logger.warning("Insufficient candle data", symbol=symbol, count=len(candles))
                    continue

                sentiment = get_symbol_sentiment(symbol, _latest_news)

                signal = await generate_signal(
                    symbol=symbol,
                    candles=candles,
                    spot_price=spot_price,
                    oi_data=oi_data,
                    sentiment_label=sentiment,
                    session=session,
                )

                if signal:
                    await session.commit()
                    await send_signal_alert(signal)
                    logger.info("Signal sent", symbol=symbol, confidence=signal.confidence)

            except Exception as e:
                logger.error("Signal engine error", symbol=symbol, error=str(e))


async def evaluate_open_signals():
    """
    Runs every minute — checks if any open signal has hit target or SL.
    Uses mock prices in mock mode.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal).where(Signal.state == SignalState.OPEN)
        )
        open_signals = result.scalars().all()

        if not open_signals:
            return

        for signal in open_signals:
            symbol = signal.symbol
            if USE_MOCK:
                current_price = get_mock_spot_price(symbol)
            else:
                from app.market_data.websocket_client import get_live_price
                current_price = get_live_price(symbol)
                if not current_price:
                    continue

            from app.signals.lifecycle import evaluate_signal_tick
            new_state = await evaluate_signal_tick(signal, current_price, session)

            if new_state:
                await session.commit()
                # Update consecutive loss counter + global circuit breaker
                if new_state == "SL_HIT":
                    _consecutive_losses[signal.symbol] = _consecutive_losses.get(signal.symbol, 0) + 1
                    if _consecutive_losses[signal.symbol] >= MAX_CONSECUTIVE_LOSSES:
                        logger.info("Consecutive loss gate triggered", symbol=signal.symbol,
                                    count=_consecutive_losses[signal.symbol])

                    global _daily_losses_total
                    _daily_losses_total += 1
                    if _daily_losses_total == MAX_DAILY_LOSSES:
                        logger.warning("Daily circuit breaker tripped — signals paused for today",
                                       total_losses=_daily_losses_total)
                        await send_text_alert(
                            f"*⚡ Circuit Breaker Triggered*\n"
                            f"3 stop-losses hit today\\. Signal generation paused for the rest of the session\\.\n"
                            f"Resume tomorrow at 9:15 AM\\."
                        )
                else:
                    _consecutive_losses[signal.symbol] = 0  # reset on win or expiry

                emoji = "🏁 TARGET HIT" if new_state == "TARGET_HIT" else "🛑 SL HIT"
                gate_note = (f"\n⚠️ _{signal.symbol} paused for today — 2 consecutive losses_"
                             if _consecutive_losses.get(signal.symbol, 0) >= MAX_CONSECUTIVE_LOSSES else "")
                await send_text_alert(
                    f"*{signal.symbol} Signal \\#{signal.id} — {emoji}*\n"
                    f"Entry: {signal.entry:.2f} | Exit: {current_price:.2f}\n"
                    f"Direction: {signal.direction.value}{gate_note}"
                )


async def fetch_news_job():
    """Runs every 15 minutes — fetches and caches latest news."""
    global _latest_news
    try:
        _latest_news = await fetch_news()
        logger.info("News refreshed", count=len(_latest_news))
    except Exception as e:
        logger.warning("News fetch failed", error=str(e))


async def expire_signals_job():
    """Runs at 15:30 IST — expires all open signals at market close."""
    async with AsyncSessionLocal() as session:
        await expire_eod_signals(session)
        await session.commit()

    # Clear candle buffers for fresh start tomorrow
    for symbol in ["NIFTY", "BANKNIFTY"]:
        clear_candles(symbol)

    stats = await get_eod_stats()
    await send_text_alert(
        f"*Chanakya Sanket — Market Closed*\n\n"
        f"Today's performance:\n"
        f"Total signals: {stats['total_signals']}\n"
        f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
        f"Win rate: {stats['win_rate']}%\n"
        f"P&L: ₹{stats['total_pnl']:,.0f}"
    )


async def get_eod_stats() -> dict:
    async with AsyncSessionLocal() as session:
        return await get_overall_stats(session)


async def token_check_job():
    """
    Runs at 8:45 IST Mon-Fri — checks if the Upstox token is valid.
    If expired, sends a Telegram reminder with the login link before market open.
    """
    from app.auth.upstox import validate_token
    valid = await validate_token()
    if not valid:
        logger.warning("Upstox token is expired or missing — sending reminder")
        await send_text_alert(
            "*⚠️ Upstox Token Expired*\n\n"
            "Market opens in 30 minutes\\. Re\\-authenticate now:\n\n"
            "1\\. Open your Mac\n"
            "2\\. Go to: `http://localhost:8000/auth/login`\n"
            "3\\. Log in to Upstox \\(takes 30 seconds\\)\n\n"
            "_Signal engine will switch to live mode automatically\\._"
        )
    else:
        logger.info("Token check passed — Upstox token is valid")


async def morning_startup_job():
    """Runs at 09:15 IST — sends market open notification and seeds initial candles."""
    logger.info("Market open — seeding initial candle data")

    global _daily_losses_total
    _daily_losses_total = 0  # reset circuit breaker for new day
    for symbol in ["NIFTY", "BANKNIFTY"]:
        clear_candles(symbol)
        _consecutive_losses[symbol] = 0  # reset loss gate for new day
        if USE_MOCK:
            generate_mock_candles(symbol, n=80)

    await send_text_alert(
        "*Chanakya Sanket — Market Open*\n"
        "Signal engine is active. Monitoring NIFTY & BANKNIFTY."
    )


async def save_oi_snapshot_job():
    """
    Runs every 5 minutes during market hours (live mode only).
    Fetches Upstox options chain OI for each symbol and persists to market_snapshots.
    This builds a historical intraday OI dataset over time for future backtest use.
    """
    if USE_MOCK:
        return
    if not can_generate_signals():
        return

    from app.market_data.websocket_client import get_live_price
    from app.market_data.options_chain import fetch_options_chain
    from app.signals.strike_selector import select_expiry
    from app.utils.regime import detect_regime
    from app.market_data.candle_processor import get_candles
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as session:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                spot_price = get_live_price(symbol)
                if not spot_price:
                    continue
                expiry = select_expiry(symbol)
                oi_data = await fetch_options_chain(symbol, expiry)
                if not oi_data:
                    continue

                candles = get_candles(symbol, limit=100)
                regime = detect_regime(candles) if len(candles) >= 20 else "TRENDING"

                snapshot = MarketSnapshot(
                    symbol=symbol,
                    price=spot_price,
                    call_oi=oi_data.get("call_oi"),
                    put_oi=oi_data.get("put_oi"),
                    regime=MarketRegime(regime),
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(snapshot)
                logger.debug("OI snapshot saved", symbol=symbol,
                             call_oi=oi_data.get("call_oi"), put_oi=oi_data.get("put_oi"))
            except Exception as e:
                logger.error("OI snapshot save failed", symbol=symbol, error=str(e))
        await session.commit()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # Signal engine — every 5 minutes during market hours (9:15 to 15:15)
    scheduler.add_job(
        run_signal_engine,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="15,20,25,30,35,40,45,50,55,0,5,10",
            timezone="Asia/Kolkata",
        ),
        id="signal_engine",
        name="Signal Engine",
        max_instances=1,
        coalesce=True,
    )

    # Open signal evaluator — every minute.
    # In mock mode: runs unconditionally (no live market needed).
    # In live mode: restricted to market hours only.
    if USE_MOCK:
        scheduler.add_job(
            evaluate_open_signals,
            IntervalTrigger(minutes=1),
            id="signal_evaluator",
            name="Signal Evaluator (mock)",
            max_instances=1,
            coalesce=True,
        )
    else:
        scheduler.add_job(
            evaluate_open_signals,
            CronTrigger(
                day_of_week="mon-fri",
                hour="9-15",
                minute="*",
                timezone="Asia/Kolkata",
            ),
            id="signal_evaluator",
            name="Signal Evaluator",
            max_instances=1,
            coalesce=True,
        )

    # News fetch — every 15 minutes
    scheduler.add_job(
        fetch_news_job,
        IntervalTrigger(minutes=15),
        id="news_fetcher",
        name="News Fetcher",
    )

    # Token check — 8:45 IST weekdays (30 min before market open)
    scheduler.add_job(
        token_check_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=8,
            minute=45,
            timezone="Asia/Kolkata",
        ),
        id="token_check",
        name="Token Check",
    )

    # Morning startup — 9:15 IST weekdays
    scheduler.add_job(
        morning_startup_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=9,
            minute=15,
            timezone="Asia/Kolkata",
        ),
        id="morning_startup",
        name="Morning Startup",
    )

    # EOD expire — 15:30 IST weekdays
    scheduler.add_job(
        expire_signals_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=30,
            timezone="Asia/Kolkata",
        ),
        id="eod_expire",
        name="EOD Signal Expiry",
    )

    # OI snapshot — every 5 minutes during market hours (live mode only)
    # Builds a historical intraday OI dataset in market_snapshots for future backtest use.
    scheduler.add_job(
        save_oi_snapshot_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="15,20,25,30,35,40,45,50,55,0,5,10",
            timezone="Asia/Kolkata",
        ),
        id="oi_snapshot",
        name="OI Snapshot",
        max_instances=1,
        coalesce=True,
    )

    return scheduler
