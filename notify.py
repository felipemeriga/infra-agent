import logging

import httpx

from config import Settings

logger = logging.getLogger(__name__)


def notify_whatsapp(message: str, settings: Settings | None = None) -> None:
    """Send a WhatsApp notification via server-guardian. Best-effort, never raises."""
    if settings is None:
        settings = Settings()

    try:
        httpx.post(
            f"{settings.guardian_url}/api/notify",
            json={"message": message, "number": "default"},
            headers={"Authorization": f"Bearer {settings.guardian_api_key}"},
            timeout=30,
        )
    except Exception:
        logger.warning("Failed to send WhatsApp notification", exc_info=True)
