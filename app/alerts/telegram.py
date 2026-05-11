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
