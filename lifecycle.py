import asyncio
import logging

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Manages graceful shutdown of background tasks.

    Tracks active tasks, provides a shutdown signal, and waits for
    in-flight work to complete within a timeout.
    """

    def __init__(self, shutdown_timeout: int = 30) -> None:
        self._shutdown_timeout = shutdown_timeout
        self._shutdown_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task] = set()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    def trigger_shutdown(self) -> None:
        """Signal that shutdown has been requested."""
        logger.info("Shutdown triggered")
        self._shutdown_event.set()

    def register_task(self, task: asyncio.Task) -> None:
        """Track an active task for shutdown draining."""
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def unregister_task(self, task: asyncio.Task) -> None:
        """Remove a task from tracking."""
        self._active_tasks.discard(task)

    async def wait_for_completion(self) -> None:
        """Wait for all active tasks to complete, up to the shutdown timeout."""
        pending = {t for t in self._active_tasks if not t.done()}

        if not pending:
            logger.info("No active tasks — shutdown complete")
            return

        logger.info(
            f"Waiting for {len(pending)} active task(s) to complete "
            f"(timeout={self._shutdown_timeout}s)"
        )

        done, still_pending = await asyncio.wait(pending, timeout=self._shutdown_timeout)

        if still_pending:
            logger.warning(f"{len(still_pending)} task(s) did not complete within timeout")
            for task in still_pending:
                task.cancel()
        else:
            logger.info("All active tasks completed before timeout")
