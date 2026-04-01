# tests/graph/test_auto_respond.py
from unittest.mock import MagicMock, patch

import httpx
import respx

# respx still needed for guardian API mocks
from throttler import NotificationThrottler


def _initial_state(service: str = "rag-backend", trigger: str = "event:die") -> dict:
    return {
        "service_name": service,
        "trigger": trigger,
        "container_status": None,
        "logs": None,
        "crash_history": None,
        "llm_decision": None,
        "action_taken": None,
        "action_succeeded": False,
        "result": None,
        "status": "",
    }


def test_auto_respond_graph_compiles():
    from graph.auto_respond import build_auto_respond_graph

    graph = build_auto_respond_graph()
    assert graph is not None


@respx.mock
def test_auto_respond_restarts_when_llm_says_restart(mock_docker_client, settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "exited"
    container.id = "abc123"
    container.image.tags = ["felipemeriga1/rag-backend:latest"]
    container.attrs = {
        "State": {
            "Status": "exited",
            "StartedAt": "2026-03-30T10:00:00Z",
            "FinishedAt": "2026-03-30T10:05:00Z",
        },
        "RestartCount": 1,
    }
    container.logs.return_value = b"ERROR: connection refused\nShutting down"
    container.stats.return_value = {
        "memory_stats": {"usage": 0, "limit": 268435456},
    }
    mock_docker_client.containers.get.return_value = container

    # LLM says restart
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": '{"decision": "restart", "reason": "Transient error, safe to restart"}'
            },
        )
    )

    # After restart, container is healthy
    container_after = MagicMock()
    container_after.status = "running"
    container_after.attrs = {
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
    }
    mock_docker_client.containers.get.side_effect = [container, container, container_after]

    from graph.auto_respond import build_auto_respond_graph

    throttler = NotificationThrottler(cooldown=900)
    graph = build_auto_respond_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            _initial_state(),
            {"configurable": {"settings": settings, "throttler": throttler}},
        )

    assert result["llm_decision"] == "restart"
    assert result["action_succeeded"] is True
    assert result["result"] is not None
    assert result["status"] in ("complete", "waiting")


@respx.mock
def test_auto_respond_escalates_when_llm_says_escalate(mock_docker_client, settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "exited"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "exited", "StartedAt": "2026-03-30T10:00:00Z"},
        "RestartCount": 5,
    }
    container.logs.return_value = b"FATAL: database migration failed\nExiting"
    container.stats.return_value = {"memory_stats": {"usage": 0, "limit": 268435456}}
    mock_docker_client.containers.get.return_value = container

    # LLM says escalate
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    '{"decision": "escalate",'
                    ' "reason": "Database migration failure requires manual intervention"}'
                )
            },
        )
    )

    # WhatsApp notification
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.auto_respond import build_auto_respond_graph

    throttler = NotificationThrottler(cooldown=900)
    graph = build_auto_respond_graph()

    result = graph.invoke(
        _initial_state(),
        {"configurable": {"settings": settings, "throttler": throttler}},
    )

    assert result["llm_decision"] == "escalate"
    assert result["action_taken"] is None or result["action_taken"] == "escalate"
    assert result["status"] == "escalated"


@respx.mock
def test_auto_respond_does_nothing_when_llm_says_wait(mock_docker_client, settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "running", "StartedAt": "2026-03-30T10:00:00Z"},
        "RestartCount": 0,
    }
    container.logs.return_value = b"INFO: health check warning, retrying"
    container.stats.return_value = {
        "memory_stats": {"usage": 100000000, "limit": 268435456},
    }
    mock_docker_client.containers.get.return_value = container

    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": '{"decision": "wait", "reason": "Transient warning, no action needed"}'
            },
        )
    )

    from graph.auto_respond import build_auto_respond_graph

    throttler = NotificationThrottler(cooldown=900)
    graph = build_auto_respond_graph()

    result = graph.invoke(
        _initial_state(trigger="monitor:memory"),
        {"configurable": {"settings": settings, "throttler": throttler}},
    )

    assert result["llm_decision"] == "wait"
    assert result["action_succeeded"] is False
    assert result["status"] == "waiting"


@respx.mock
def test_auto_respond_reports_when_restart_fails(mock_docker_client, settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "exited"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "exited", "StartedAt": "2026-03-30T10:00:00Z"},
        "RestartCount": 2,
    }
    container.logs.return_value = b"ERROR: segfault"
    container.stats.return_value = {"memory_stats": {"usage": 0, "limit": 268435456}}
    mock_docker_client.containers.get.return_value = container

    # LLM says restart
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={"response": '{"decision": "restart", "reason": "Try restart"}'},
        )
    )

    # After restart, container is still unhealthy
    container_after = MagicMock()
    container_after.status = "running"
    container_after.attrs = {
        "State": {"Status": "running", "Health": {"Status": "unhealthy"}},
    }
    mock_docker_client.containers.get.side_effect = [container, container, container_after]

    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.auto_respond import build_auto_respond_graph

    throttler = NotificationThrottler(cooldown=900)
    graph = build_auto_respond_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            _initial_state(),
            {"configurable": {"settings": settings, "throttler": throttler}},
        )

    assert result["action_succeeded"] is False
    assert result["result"] is not None
    assert result["status"] == "escalated"


def test_auto_respond_uses_wait_when_circuit_open(mock_docker_client, settings):
    from circuit_breaker import CircuitBreaker

    container = MagicMock()
    container.name = "rag-backend"
    container.status = "exited"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "exited", "StartedAt": "2026-03-30T10:00:00Z"},
        "RestartCount": 0,
    }
    container.logs.return_value = b"ERROR: crash"
    container.stats.return_value = {"memory_stats": {"usage": 0, "limit": 268435456}}
    mock_docker_client.containers.get.return_value = container

    from graph.auto_respond import build_auto_respond_graph

    # Create a circuit breaker that is already open
    cb = CircuitBreaker(max_failures=1, timeout=60)
    try:
        cb.call(lambda: (_ for _ in ()).throw(ConnectionError("down")))
    except ConnectionError:
        pass

    throttler = NotificationThrottler(cooldown=900)
    graph = build_auto_respond_graph()

    result = graph.invoke(
        _initial_state(),
        {"configurable": {"settings": settings, "throttler": throttler, "circuit_breaker": cb}},
    )

    assert result["llm_decision"] == "wait"
    assert result["status"] == "waiting"
