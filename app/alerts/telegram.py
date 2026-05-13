import structlog
import httpx
from app.config import get_settings
from app.db.models import Signal

logger = structlog.get_logger()
settings = get_settings()

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


REASON_LABELS = {
    "vwap_breakout":          "VWAP Breakout",
    "rsi_momentum":           "RSI Momentum",
    "bullish_engulfing":      "Bullish Engulfing",
    "bearish_engulfing":      "Bearish Engulfing",
    "opening_range_breakout": "Opening Range Breakout",
    "oi_buildup":             "OI Buildup",
    "positive_sentiment":     "Positive News",
    "negative_sentiment":     "Negative News",
}


def format_signal_message(signal: Signal) -> str:
    is_call = signal.direction.value == "CALL"
    dir_emoji = "🟢" if is_call else "🔴"
    dir_label = "CALL  (BUY CE)" if is_call else "PUT  (BUY PE)"
    conf_bar = "🔵" * (signal.confidence // 10) + "⚫" * (10 - signal.confidence // 10)
    regime_emoji = "📈" if signal.regime.value == "TRENDING" else "📊"

    reasons_text = "\n".join(
        f"  ✅ {REASON_LABELS.get(r, r.replace('_', ' ').title())}  +{pts}pts"
        for r, pts in signal.reasons.items()
    )

    return f"""
{dir_emoji} *{signal.symbol}  —  {dir_label}*
\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015

🎯 *Strike:* `{signal.strike:.0f}`   📅 *Expiry:* `{signal.expiry}`

💰 *Entry:*       `{signal.entry:.2f}`
🛑 *Stop Loss:* `{signal.stop_loss:.2f}`
🏁 *Target:*      `{signal.target:.2f}`

📊 *Confidence:* {conf_bar} *{signal.confidence}%*
{regime_emoji} *Regime:* {signal.regime.value.title()}

🧠 *Why this signal?*
{reasons_text}

💼 *Capital:* ₹{signal.capital_required:,.0f}   *Lots:* {signal.suggested_lots}
🔖 _Signal #{signal.id}_

_⚠️ Paper trade only — do not auto-execute_
""".strip()


async def send_signal_alert(signal: Signal) -> bool:
    message = format_signal_message(signal)
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram alert sent", signal_id=signal.id)
            return True
        except Exception as e:
            logger.error("Telegram alert failed", signal_id=signal.id, error=str(e))
            return False


async def send_squareoff_alert(signal: Signal, current_price: float, minutes_left: int) -> bool:
    """Send a near-expiry square-off warning with live P&L and an inline 'Mark as Sold' button."""
    is_call = signal.direction.value == "CALL"
    if is_call:
        unrealized = (current_price - signal.entry) * signal.suggested_lots
    else:
        unrealized = (signal.entry - current_price) * signal.suggested_lots

    pnl_emoji = "📈" if unrealized >= 0 else "📉"
    pnl_sign = "+" if unrealized >= 0 else ""
    dir_label = "CALL (BUY CE)" if is_call else "PUT (BUY PE)"

    text = (
        f"⚠️ *{signal.symbol} Signal #{signal.id} — Square Off in {minutes_left} min!*\n\n"
        f"{dir_label} | Strike: `{signal.strike:.0f}` | Expiry: `{signal.expiry}`\n\n"
        f"Entry: `{signal.entry:.1f}` → Now: `{current_price:.1f}`\n"
        f"{pnl_emoji} Unrealized P&L: *{pnl_sign}₹{unrealized:,.0f}*\n\n"
        f"🏁 Target: `{signal.target:.1f}` | 🛑 SL: `{signal.stop_loss:.1f}`\n\n"
        f"_Auto-expires at 3:30 PM if not closed._"
    )

    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "✅ Mark as Sold", "callback_data": f"sold_{signal.id}"}
                    ]]
                },
            }, timeout=10)
            resp.raise_for_status()
            logger.info("Squareoff alert sent", signal_id=signal.id, minutes_left=minutes_left)
            return True
        except Exception as e:
            logger.error("Squareoff alert failed", signal_id=signal.id, error=str(e))
            return False


async def answer_callback_query(callback_query_id: str, text: str) -> None:
    """Acknowledge a Telegram inline button press (removes the loading spinner)."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={
                "callback_query_id": callback_query_id,
                "text": text,
            }, timeout=5)
        except Exception:
            pass


async def send_text_alert(text: str) -> bool:
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Telegram message failed", error=str(e))
            return False
