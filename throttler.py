# throttler.py
import logging
import time

logger = logging.getLogger(__name__)


class NotificationThrottler:
    """In-memory notification cooldown tracker.

    Prevents duplicate alerts for the same service + event type
    within a configurable cooldown period.
    """

    def __init__(self, cooldown: int = 900) -> None:
        self._cooldown = cooldown
        self._last_notified: dict[str, dict[str, float]] = {}

    def _key(self, service: str, event_type: str) -> tuple[str, str]:
        return service, event_type

    def should_notify(self, service: str, event_type: str, force: bool = False) -> bool:
        """Check if a notification should be sent."""
        if force:
            return True

        service_events = self._last_notified.get(service, {})
        last_time = service_events.get(event_type)

        if last_time is None:
            return True

        return (time.time() - last_time) >= self._cooldown

    def record(self, service: str, event_type: str) -> None:
        """Record that a notification was sent."""
        if service not in self._last_notified:
            self._last_notified[service] = {}
        self._last_notified[service][event_type] = time.time()

    def clear(self, service: str) -> None:
        """Clear all cooldowns for a service."""
        self._last_notified.pop(service, None)
