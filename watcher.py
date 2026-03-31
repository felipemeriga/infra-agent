# watcher.py
import asyncio
import logging
import uuid

import docker

from config import Settings
from graph.auto_respond import build_auto_respond_graph
from lifecycle import LifecycleManager
from throttler import NotificationThrottler

logger = logging.getLogger(__name__)

ACTIONABLE_EVENTS = {"die", "oom", "health_status: unhealthy"}


class ExpectedStopTracker:
    """Track container stops that were initiated by our own workflows.

    When deploy or restart workflows stop a container, they register
    it here so the event watcher knows to ignore the resulting 'die' event.
    """

    def __init__(self) -> None:
        self._expected: set[str] = set()

    def expect(self, service_name: str) -> None:
        """Mark a service as expected to stop."""
        self._expected.add(service_name)

    def is_expected(self, service_name: str) -> bool:
        """Check and consume an expected stop. Returns True once, then False."""
        if service_name in self._expected:
            self._expected.discard(service_name)
            return True
        return False


def parse_docker_event(raw: dict) -> dict | None:
    """Parse a raw Docker event into a structured dict, or None if irrelevant."""
    if raw.get("Type") != "container":
        return None

    action = raw.get("Action", "")
    if action not in ACTIONABLE_EVENTS:
        return None

    name = raw.get("Actor", {}).get("Attributes", {}).get("name", "")
    if not name:
        return None

    return {
        "service": name,
        "action": action,
        "time": raw.get("time", 0),
    }


def is_protected_service(name: str, settings: Settings) -> bool:
    """Check if a service is in the protected services list."""
    return name in settings.protected_services


async def docker_event_watcher(
    settings: Settings,
    throttler: NotificationThrottler,
    expected_stops: ExpectedStopTracker | None = None,
    lifecycle: LifecycleManager | None = None,
    circuit_breaker=None,
) -> None:
    """Watch Docker events and trigger auto_respond for actionable events.

    Runs indefinitely as an async background task.
    """
    if expected_stops is None:
        expected_stops = ExpectedStopTracker()

    client = docker.from_env()
    logger.info("Docker event watcher started")

    while True:
        if lifecycle and lifecycle.is_shutting_down:
            logger.info("Docker event watcher stopping — shutdown requested")
            return

        try:
            for raw_event in client.events(decode=True):
                if lifecycle and lifecycle.is_shutting_down:
                    logger.info("Docker event watcher stopping — shutdown requested")
                    return

                event = parse_docker_event(raw_event)
                if event is None:
                    continue

                service = event["service"]

                if is_protected_service(service, settings):
                    logger.debug(f"Ignoring event for protected service: {service}")
                    continue

                if expected_stops.is_expected(service):
                    logger.info(f"Ignoring expected stop for: {service}")
                    continue

                logger.info(f"Actionable event: {event['action']} for {service}")

                task = asyncio.create_task(
                    _handle_event(service, event["action"], settings, throttler, circuit_breaker)
                )
                if lifecycle:
                    lifecycle.register_task(task)

        except Exception:
            logger.error("Docker event watcher error, restarting in 5s", exc_info=True)
            await asyncio.sleep(5)


async def _handle_event(
    service: str,
    action: str,
    settings: Settings,
    throttler: NotificationThrottler,
    circuit_breaker=None,
) -> None:
    """Run auto_respond graph for a detected event."""
    try:
        graph = build_auto_respond_graph()
        thread_id = f"auto:{service}:{uuid.uuid4()}"
        await asyncio.to_thread(
            graph.invoke,
            {
                "service_name": service,
                "trigger": f"event:{action}",
                "container_status": None,
                "logs": None,
                "crash_history": None,
                "llm_decision": None,
                "action_taken": None,
                "action_succeeded": False,
                "result": None,
            },
            {
                "configurable": {
                    "settings": settings,
                    "throttler": throttler,
                    "circuit_breaker": circuit_breaker,
                    "thread_id": thread_id,
                }
            },
        )
    except Exception:
        logger.error(f"Auto-respond failed for {service}", exc_info=True)
