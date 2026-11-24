"""
Alert dispatch — Telegram + Email (Resend).
"""
import logging
from typing import List
import httpx

from app.core.config import settings
from app.ml.signal_engine import SignalResult

logger = logging.getLogger(__name__)


def format_signal_message(signal: SignalResult) -> str:
    direction = "🟢 BUY" if signal.direction == 1 else "🔴 SELL"
    vol_bar = "🔥" * min(5, int(signal.volume_ratio))
    top_reasons = "\n".join(f"  • {r}" for r in signal.reasons[:3])
    return (
        f"{direction} {signal.symbol} ({signal.exchange})\n"
        f"Price: ₹{signal.price:,.2f}\n"
        f"Confidence: {signal.confidence * 100:.0f}%\n"
        f"Volume: {signal.volume_ratio:.1f}x avg {vol_bar}\n"
        f"Why:\n{top_reasons}"
    )


async def send_telegram(chat_id: str, message: str):
    """Send a message via Telegram Bot API."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
        except Exception as e:
            logger.error(f"Telegram send error: {e}")


async def send_email(to: str, subject: str, body: str):
    """Send email via Resend API."""
    if not settings.RESEND_API_KEY:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                },
            )
        except Exception as e:
            logger.error(f"Email send error: {e}")


async def dispatch_alerts(signals: List[SignalResult]):
    """
    Dispatch alerts for high-confidence signals.
    In production: query alert_rules table, match users, send per channel.
    """
    for signal in signals:
        msg = format_signal_message(signal)
        logger.info(f"Alert dispatched: {signal.symbol} {signal.direction}")
        # TODO: query DB for users watching this symbol with matching alert rules
        # For now, log — wire up user queries once DB is connected
