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
from app.db.models import Signal, SignalState
from sqlalchemy import select

logger = structlog.get_logger()
settings = get_settings()

# Track if we're using mock data
USE_MOCK = not bool(settings.upstox_access_token)

# Cache latest news articles
_latest_news: list[dict] = []


async def run_signal_engine():
    """
    Core job — runs every 5 minutes during market hours.
    For each symbol: fetch candles → check regime → run strategies → generate signal → alert.
    """
    if not can_generate_signals():
        logger.debug("Outside signal generation window — skipping")
        return

    logger.info("Signal engine running", mock=USE_MOCK)

    async with AsyncSessionLocal() as session:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                if USE_MOCK:
                    generate_mock_candles(symbol, n=5)  # Add 5 new mock candles
                    spot_price = get_mock_spot_price(symbol)
                    oi_data = get_mock_oi_data(symbol)
                else:
                    from app.market_data.options_chain import fetch_options_chain
                    from app.signals.strike_selector import select_expiry
                    expiry = select_expiry(symbol)
                    oi_data = await fetch_options_chain(symbol, expiry)
                    spot_price = get_mock_spot_price(symbol)  # TODO: replace with live price

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
            current_price = get_mock_spot_price(symbol) if USE_MOCK else get_mock_spot_price(symbol)

            from app.signals.lifecycle import evaluate_signal_tick
            new_state = await evaluate_signal_tick(signal, current_price, session)

            if new_state:
                await session.commit()
                emoji = "TARGET HIT" if new_state == "TARGET_HIT" else "SL HIT"
                await send_text_alert(
                    f"*{signal.symbol} Signal #{signal.id} — {emoji}*\n"
                    f"Entry: {signal.entry} | Exit: {current_price:.2f}\n"
                    f"Direction: {signal.direction.value}"
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


async def morning_startup_job():
    """Runs at 09:15 IST — sends market open notification and seeds initial candles."""
    logger.info("Market open — seeding initial candle data")

    for symbol in ["NIFTY", "BANKNIFTY"]:
        clear_candles(symbol)
        if USE_MOCK:
            generate_mock_candles(symbol, n=80)

    await send_text_alert(
        "*Chanakya Sanket — Market Open*\n"
        "Signal engine is active. Monitoring NIFTY & BANKNIFTY."
    )


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

    # Open signal evaluator — every minute during market hours
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

    return scheduler
