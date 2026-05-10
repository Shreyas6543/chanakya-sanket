import structlog
import httpx
from app.config import get_settings
from app.db.models import Signal

logger = structlog.get_logger()
settings = get_settings()

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_signal_message(signal: Signal) -> str:
    direction_emoji = "CALL" if signal.direction.value == "CALL" else "PUT"
    reasons_text = "\n".join(
        f"  • {reason.replace('_', ' ').title()}: +{pts}pts"
        for reason, pts in signal.reasons.items()
    )

    return f"""
*{signal.symbol} {direction_emoji} SIGNAL*

Strike: `{signal.strike:.0f}`  |  Expiry: `{signal.expiry}`
Entry: `{signal.entry:.2f}`
Stop Loss: `{signal.stop_loss:.2f}`
Target: `{signal.target:.2f}`

Confidence: *{signal.confidence}%*
Regime: {signal.regime.value}

Reasons:
{reasons_text}

Capital Required: ₹{signal.capital_required:,.0f}
Suggested Lots: {signal.suggested_lots}
Signal ID: #{signal.id}

_Paper trade only — do not auto-execute_
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
