# monitor.py
import asyncio
import logging
import uuid

import docker

from config import Settings
from graph.auto_respond import build_auto_respond_graph
from lifecycle import LifecycleManager
from throttler import NotificationThrottler
from watcher import is_protected_service

logger = logging.getLogger(__name__)


class StrikeTracker:
    """Track consecutive threshold breaches per service.

    Requires N consecutive strikes before triggering action,
    preventing false positives from transient spikes.
    """

    def __init__(self, threshold: int = 2) -> None:
        self._threshold = threshold
        self._strikes: dict[str, dict[str, int]] = {}

    def record_strike(self, service: str, check_type: str) -> bool:
        """Record a strike. Returns True if threshold reached."""
        if service not in self._strikes:
            self._strikes[service] = {}
        count = self._strikes[service].get(check_type, 0) + 1
        self._strikes[service][check_type] = count
        return count >= self._threshold

    def clear(self, service: str, check_type: str) -> None:
        """Clear strikes for a service+check_type (issue resolved)."""
        if service in self._strikes:
            self._strikes[service].pop(check_type, None)


def check_container_health(container, settings: Settings) -> dict:
    """Check a single container for health issues. Returns a dict of findings."""
    name = container.name
    result = {
        "name": name,
        "memory_alert": False,
        "memory_pct": 0.0,
        "restart_loop": False,
        "restart_count": 0,
    }

    # Check memory
    try:
        stats = container.stats(stream=False)
        mem = stats.get("memory_stats", {})
        usage = mem.get("usage", 0)
        limit = mem.get("limit", 0)
        if limit > 0:
            pct = (usage / limit) * 100
            result["memory_pct"] = round(pct, 1)
            result["memory_alert"] = pct > settings.memory_threshold_pct
    except Exception:
        logger.debug(f"Could not get stats for {name}")

    # Check restart count
    restart_count = container.attrs.get("RestartCount", 0)
    result["restart_count"] = restart_count
    result["restart_loop"] = restart_count >= settings.max_restarts_count

    return result


async def health_monitor(
    settings: Settings,
    throttler: NotificationThrottler,
    lifecycle: LifecycleManager | None = None,
    circuit_breaker=None,
) -> None:
    """Periodic health check on all running containers.

    Runs every settings.monitor_interval seconds as an async background task.
    Uses a strike system to avoid false positives from transient spikes.
    """
    strikes = StrikeTracker(threshold=settings.strike_threshold)
    logger.info(
        f"Health monitor started (interval={settings.monitor_interval}s, "
        f"memory_threshold={settings.memory_threshold_pct}%)"
    )

    while True:
        if lifecycle and lifecycle.is_shutting_down:
            logger.info("Health monitor stopping — shutdown requested")
            return

        try:
            client = docker.from_env()
            containers = client.containers.list()

            for container in containers:
                name = container.name
                if is_protected_service(name, settings):
                    continue

                health = check_container_health(container, settings)

                if health["memory_alert"]:
                    if strikes.record_strike(name, "memory"):
                        logger.warning(f"Memory alert for {name}: {health['memory_pct']}%")
                        await _trigger_auto_respond(
                            name,
                            f"monitor:memory:{health['memory_pct']}%",
                            settings,
                            throttler,
                            circuit_breaker,
                        )
                else:
                    strikes.clear(name, "memory")

                if health["restart_loop"]:
                    if strikes.record_strike(name, "restart_loop"):
                        logger.warning(
                            f"Restart loop detected for {name}: {health['restart_count']} restarts"
                        )
                        await _trigger_auto_respond(
                            name,
                            f"monitor:restart_loop:{health['restart_count']}",
                            settings,
                            throttler,
                            circuit_breaker,
                        )
                else:
                    strikes.clear(name, "restart_loop")

        except Exception:
            logger.error("Health monitor error", exc_info=True)

        await asyncio.sleep(settings.monitor_interval)


async def _trigger_auto_respond(
    service: str,
    trigger: str,
    settings: Settings,
    throttler: NotificationThrottler,
    circuit_breaker=None,
) -> None:
    """Run auto_respond graph for a health monitor detection."""
    try:
        graph = build_auto_respond_graph()
        thread_id = f"auto:{service}:{uuid.uuid4()}"
        await asyncio.to_thread(
            graph.invoke,
            {
                "service_name": service,
                "trigger": trigger,
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
