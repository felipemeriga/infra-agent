import json
from unittest.mock import MagicMock

import httpx
import pytest
import respx


@pytest.fixture()
def mock_docker_for_diagnose(mock_docker_client):
    container = MagicMock()
    container.name = "rag-backend"
    container.status = "running"
    container.image.tags = ["felipemeriga1/rag-backend:latest"]
    container.attrs = {
        "State": {"Status": "running", "StartedAt": "2026-03-30T10:00:00Z"},
        "HostConfig": {"Memory": 268435456},
        "Config": {"Image": "felipemeriga1/rag-backend:latest"},
    }
    container.stats.return_value = {
        "memory_stats": {"usage": 245000000, "limit": 268435456},
        "cpu_stats": {"cpu_usage": {"total_usage": 100000}},
        "precpu_stats": {"cpu_usage": {"total_usage": 90000}},
    }
    container.logs.return_value = b"ERROR: Database connection timeout\nRetrying..."
    mock_docker_client.containers.get.return_value = container
    return mock_docker_client


def test_diagnose_graph_compiles():
    from graph.diagnose import build_diagnose_graph

    graph = build_diagnose_graph()
    assert graph is not None


@respx.mock
def test_diagnose_runs_full_pipeline(mock_docker_for_diagnose, settings, tmp_path):
    # Mock traefik
    respx.get("http://traefik:8080/api/http/routers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "name": "rag-backend@docker",
                    "rule": "Host(`api.example.com`)",
                    "status": "enabled",
                }
            ],
        )
    )
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

    # Mock compose file
    compose_file = tmp_path / "rag-docker-compose.yml"
    compose_file.write_text(
        "services:\n  rag-backend:\n    image: felipemeriga1/rag-backend:latest\n"
    )

    # Mock LLM response
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "diagnosis": (
                            "The container is running but logs show"
                            " database connection timeout."
                            " Memory usage is near limit."
                        ),
                        "recommended_actions": [
                            "Increase memory limit",
                            "Check database connectivity",
                        ],
                    }
                )
            },
        )
    )

    from graph.diagnose import build_diagnose_graph

    graph = build_diagnose_graph()
    result = graph.invoke(
        {
            "service_name": "rag-backend",
            "container_status": None,
            "container_stats": None,
            "logs": None,
            "traefik_status": None,
            "compose_config": None,
            "diagnosis": None,
            "recommended_actions": [],
        },
        {"configurable": {"settings": settings, "compose_dir": str(tmp_path)}},
    )

    assert result["container_status"] is not None
    assert result["logs"] is not None
    assert result["diagnosis"] is not None
    assert len(result["recommended_actions"]) > 0


@respx.mock
def test_diagnose_handles_missing_container(mock_docker_client, settings, tmp_path):
    from docker.errors import NotFound

    mock_docker_client.containers.get.side_effect = NotFound("not found")

    # Mock LLM
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "diagnosis": "Container not found",
                        "recommended_actions": ["Check if service is deployed"],
                    }
                )
            },
        )
    )
    # Mock traefik
    respx.get("http://traefik:8080/api/http/routers").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(200, json=[])
    )

    from graph.diagnose import build_diagnose_graph

    graph = build_diagnose_graph()
    result = graph.invoke(
        {
            "service_name": "nonexistent",
            "container_status": None,
            "container_stats": None,
            "logs": None,
            "traefik_status": None,
            "compose_config": None,
            "diagnosis": None,
            "recommended_actions": [],
        },
        {"configurable": {"settings": settings, "compose_dir": str(tmp_path)}},
    )

    assert result["container_status"] is not None
    status_str = json.dumps(result["container_status"]).lower()
    assert "not found" in status_str or "not_found" in status_str
