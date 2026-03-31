import time
from unittest.mock import patch

import pytest


class TestCircuitBreaker:
    def test_starts_closed(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=60)
        assert cb.state == "closed"

    def test_stays_closed_on_success(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=60)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == "closed"

    def test_stays_closed_below_threshold(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=60)

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        assert cb.state == "closed"

    def test_opens_after_max_failures(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=60)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        assert cb.state == "open"

    def test_open_raises_circuit_open_error(self):
        from circuit_breaker import CircuitBreaker, CircuitOpenError

        cb = CircuitBreaker(max_failures=3, timeout=60)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "ok")

    def test_transitions_to_half_open_after_timeout(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=10)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        assert cb.state == "open"

        with patch("time.monotonic", return_value=time.monotonic() + 11):
            assert cb.state == "half_open"

    def test_half_open_success_closes_circuit(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=10)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        with patch("time.monotonic", return_value=time.monotonic() + 11):
            result = cb.call(lambda: "recovered")
            assert result == "recovered"
            assert cb.state == "closed"

    def test_half_open_failure_reopens_circuit(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=10)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        with patch("time.monotonic", return_value=time.monotonic() + 11):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)
            assert cb.state == "open"

    def test_success_resets_failure_count(self):
        from circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, timeout=60)

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        cb.call(lambda: "ok")

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(self._failing_func)

        assert cb.state == "closed"

    @staticmethod
    def _failing_func():
        raise ValueError("connection refused")
