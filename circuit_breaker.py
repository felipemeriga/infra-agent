import logging
import time

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""


class CircuitBreaker:
    """Circuit breaker for external service calls.

    States:
    - closed: calls pass through, failures tracked
    - open: calls rejected immediately, waiting for timeout
    - half_open: one probe call allowed to test recovery
    """

    def __init__(self, max_failures: int = 3, timeout: int = 60) -> None:
        self._max_failures = max_failures
        self._timeout = timeout
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open":
            if (time.monotonic() - self._last_failure_time) >= self._timeout:
                return "half_open"
        return self._state

    def call(self, func, *args, **kwargs):
        """Execute func through the circuit breaker."""
        current_state = self.state

        if current_state == "open":
            raise CircuitOpenError(f"Circuit breaker is open (failures={self._failure_count})")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state != "closed":
            logger.info("Circuit breaker recovered — closing circuit")
        self._failure_count = 0
        self._state = "closed"

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self._max_failures:
            if self._state != "open":
                logger.warning(f"Circuit breaker opened after {self._failure_count} failures")
            self._state = "open"
