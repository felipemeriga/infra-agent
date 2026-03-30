# tests/test_monitor.py
from unittest.mock import MagicMock

import pytest

from config import Settings


@pytest.fixture()
def monitor_settings(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://guardian:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-key")
    monkeypatch.setenv("MONITOR_INTERVAL", "60")
    monkeypatch.setenv("MEMORY_THRESHOLD_PCT", "90")
    monkeypatch.setenv("MAX_RESTARTS_COUNT", "3")
    monkeypatch.setenv("MAX_RESTARTS_WINDOW", "600")
    monkeypatch.setenv("STRIKE_THRESHOLD", "2")
    return Settings()


def test_check_container_memory_below_threshold(mock_docker_client, monitor_settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.attrs = {
        "State": {"Status": "running"},
        "RestartCount": 0,
    }
    container.stats.return_value = {
        "memory_stats": {"usage": 100_000_000, "limit": 268_435_456},
    }

    from monitor import check_container_health

    result = check_container_health(container, monitor_settings)
    assert result["memory_alert"] is False
    assert result["restart_loop"] is False


def test_check_container_memory_above_threshold(mock_docker_client, monitor_settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.attrs = {
        "State": {"Status": "running"},
        "RestartCount": 0,
    }
    container.stats.return_value = {
        "memory_stats": {"usage": 250_000_000, "limit": 268_435_456},
    }

    from monitor import check_container_health

    result = check_container_health(container, monitor_settings)
    assert result["memory_alert"] is True
    assert result["memory_pct"] > 90


def test_check_container_restart_loop(mock_docker_client, monitor_settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.attrs = {
        "State": {"Status": "running"},
        "RestartCount": 5,
    }
    container.stats.return_value = {
        "memory_stats": {"usage": 100_000_000, "limit": 268_435_456},
    }

    from monitor import check_container_health

    result = check_container_health(container, monitor_settings)
    assert result["restart_loop"] is True


def test_strike_tracker_requires_consecutive_breaches():
    from monitor import StrikeTracker

    tracker = StrikeTracker(threshold=2)
    assert tracker.record_strike("rag-backend", "memory") is False  # 1st
    assert tracker.record_strike("rag-backend", "memory") is True  # 2nd -> trigger


def test_strike_tracker_resets_on_clear():
    from monitor import StrikeTracker

    tracker = StrikeTracker(threshold=2)
    tracker.record_strike("rag-backend", "memory")
    tracker.clear("rag-backend", "memory")
    assert tracker.record_strike("rag-backend", "memory") is False  # reset to 1st


def test_strike_tracker_independent_per_service():
    from monitor import StrikeTracker

    tracker = StrikeTracker(threshold=2)
    tracker.record_strike("rag-backend", "memory")
    assert tracker.record_strike("rag-frontend", "memory") is False  # different service
