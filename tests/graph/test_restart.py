from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx


@pytest.fixture()
def healthy_container(mock_docker_client):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
    }
    mock_docker_client.containers.get.return_value = container
    return container


def test_restart_graph_compiles():
    from graph.restart import build_restart_graph

    graph = build_restart_graph()
    assert graph is not None


@respx.mock
def test_restart_succeeds_on_healthy_container(healthy_container, settings):
    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "name": "rag-backend@docker",
                    "status": "enabled",
                    "serverStatus": {"http://172.18.0.5:8000": "UP"},
                }
            ],
        )
    )
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.restart import build_restart_graph

    graph = build_restart_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            {
                "service_name": "rag-backend",
                "pre_status": None,
                "post_status": None,
                "health_ok": False,
                "attempt": 0,
                "max_attempts": 3,
                "result": None,
                "status": "",
            },
            {"configurable": {"settings": settings}},
        )

    assert result["health_ok"] is True
    assert result["result"] is not None
    assert "success" in result["result"].lower() or "restarted" in result["result"].lower()
    healthy_container.restart.assert_called_once()
    assert result["status"] == "healthy"


@respx.mock
def test_restart_refuses_protected_service(mock_docker_client, settings):
    from graph.restart import build_restart_graph

    graph = build_restart_graph()
    result = graph.invoke(
        {
            "service_name": "traefik",
            "pre_status": None,
            "post_status": None,
            "health_ok": False,
            "attempt": 0,
            "max_attempts": 3,
            "result": None,
            "status": "",
        },
        {"configurable": {"settings": settings}},
    )

    assert "protected" in result["result"].lower() or "refused" in result["result"].lower()
    assert result["status"] == "error"


@respx.mock
def test_restart_escalates_after_max_attempts(mock_docker_client, settings):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.id = "abc123"
    container.attrs = {
        "State": {"Status": "running", "Health": {"Status": "unhealthy"}},
    }
    mock_docker_client.containers.get.return_value = container

    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.restart import build_restart_graph

    graph = build_restart_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            {
                "service_name": "rag-backend",
                "pre_status": None,
                "post_status": None,
                "health_ok": False,
                "attempt": 0,
                "max_attempts": 3,
                "result": None,
                "status": "",
            },
            {"configurable": {"settings": settings}},
        )

    assert result["health_ok"] is False
    assert result["result"] is not None
    assert "fail" in result["result"].lower() or "escalat" in result["result"].lower()
    assert result["status"] == "escalated"
