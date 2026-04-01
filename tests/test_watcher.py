# tests/test_watcher.py
import json

import pytest


@pytest.fixture()
def mock_event_stream():
    """Create a mock Docker event stream."""

    async def _make_stream(events: list[dict]):
        for event in events:
            yield json.dumps(event).encode("utf-8")

    return _make_stream


def test_parse_docker_event_die():
    from watcher import parse_docker_event

    raw = {
        "Type": "container",
        "Action": "die",
        "Actor": {"Attributes": {"name": "rag-backend"}},
        "time": 1711800000,
    }
    event = parse_docker_event(raw)
    assert event is not None
    assert event["service"] == "rag-backend"
    assert event["action"] == "die"


def test_parse_docker_event_oom():
    from watcher import parse_docker_event

    raw = {
        "Type": "container",
        "Action": "oom",
        "Actor": {"Attributes": {"name": "rag-backend"}},
        "time": 1711800000,
    }
    event = parse_docker_event(raw)
    assert event is not None
    assert event["action"] == "oom"


def test_parse_docker_event_health_unhealthy():
    from watcher import parse_docker_event

    raw = {
        "Type": "container",
        "Action": "health_status: unhealthy",
        "Actor": {"Attributes": {"name": "rag-backend"}},
        "time": 1711800000,
    }
    event = parse_docker_event(raw)
    assert event is not None
    assert event["action"] == "health_status: unhealthy"


def test_parse_docker_event_ignores_irrelevant():
    from watcher import parse_docker_event

    raw = {
        "Type": "container",
        "Action": "start",
        "Actor": {"Attributes": {"name": "rag-backend"}},
        "time": 1711800000,
    }
    event = parse_docker_event(raw)
    assert event is None


def test_parse_docker_event_ignores_non_container():
    from watcher import parse_docker_event

    raw = {
        "Type": "network",
        "Action": "connect",
        "Actor": {"Attributes": {"name": "bridge"}},
        "time": 1711800000,
    }
    event = parse_docker_event(raw)
    assert event is None


def test_is_protected_service(settings):
    from watcher import is_protected_service

    assert is_protected_service("server-guardian", settings) is True
    assert is_protected_service("rag-backend", settings) is False


def test_is_expected_stop():
    from watcher import ExpectedStopTracker

    tracker = ExpectedStopTracker()
    tracker.expect("rag-backend")
    assert tracker.is_expected("rag-backend") is True
    assert tracker.is_expected("rag-backend") is False  # consumed
    assert tracker.is_expected("rag-frontend") is False
