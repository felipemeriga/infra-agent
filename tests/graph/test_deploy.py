from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx


@pytest.fixture()
def deploy_mocks(mock_docker_client):
    """Set up Docker mocks for deploy tests."""
    old_container = MagicMock()
    old_container.name = "rag-backend"
    old_container.id = "old-abc123"
    old_container.status = "running"
    old_container.attrs = {
        "Config": {
            "Image": "felipemeriga1/rag-backend:v1",
            "Env": ["DATABASE_URL=postgres://db:5432/rag", "PORT=8000"],
            "Labels": {"app": "rag-backend"},
        },
        "HostConfig": {
            "PortBindings": {"8000/tcp": [{"HostPort": "8000"}]},
            "Binds": ["/data:/app/data:rw"],
            "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
            "NetworkMode": "guardian-net",
        },
        "NetworkSettings": {
            "Networks": {
                "guardian-net": {"NetworkID": "net123"},
            }
        },
    }

    new_container = MagicMock()
    new_container.name = "rag-backend"
    new_container.id = "new-def456"
    new_container.status = "running"
    new_container.attrs = {
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
    }

    mock_docker_client.containers.get.return_value = old_container
    mock_docker_client.containers.run.return_value = new_container

    image = MagicMock()
    image.tags = ["felipemeriga1/rag-backend:latest"]
    mock_docker_client.images.pull.return_value = image

    return {
        "client": mock_docker_client,
        "old_container": old_container,
        "new_container": new_container,
    }


def test_deploy_graph_compiles():
    from graph.deploy import build_deploy_graph

    graph = build_deploy_graph()
    assert graph is not None


@respx.mock
def test_deploy_succeeds(deploy_mocks, settings):
    old = deploy_mocks["old_container"]
    new = deploy_mocks["new_container"]
    client = deploy_mocks["client"]

    # After stop_old removes old container, get should return new
    client.containers.get.side_effect = [old, new, new]

    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(
            200,
            json=[{"name": "rag-backend@docker", "serverStatus": {"http://172.18.0.5:8000": "UP"}}],
        )
    )
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.deploy import build_deploy_graph

    graph = build_deploy_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            {
                "service_name": "rag-backend",
                "image_tag": "latest",
                "old_container_id": None,
                "new_container_id": None,
                "health_status": "unknown",
                "rollback_needed": False,
                "attempt": 0,
                "max_attempts": 3,
                "result": None,
                "status": "",
            },
            {"configurable": {"settings": settings}},
        )

    assert result["result"] is not None
    assert "success" in result["result"].lower()
    assert result["rollback_needed"] is False
    client.images.pull.assert_called_once()
    assert result["status"] == "success"


@respx.mock
def test_deploy_refuses_protected_service(mock_docker_client, settings):
    from graph.deploy import build_deploy_graph

    graph = build_deploy_graph()
    result = graph.invoke(
        {
            "service_name": "server-guardian",
            "image_tag": "latest",
            "old_container_id": None,
            "new_container_id": None,
            "health_status": "unknown",
            "rollback_needed": False,
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
def test_deploy_rolls_back_on_unhealthy(deploy_mocks, settings):
    old = deploy_mocks["old_container"]
    new = deploy_mocks["new_container"]
    client = deploy_mocks["client"]

    new.attrs = {
        "State": {"Status": "running", "Health": {"Status": "unhealthy"}},
    }
    new.status = "running"
    client.containers.get.side_effect = [old, new, new, new, new]

    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from graph.deploy import build_deploy_graph

    graph = build_deploy_graph()

    with patch("time.sleep"):
        result = graph.invoke(
            {
                "service_name": "rag-backend",
                "image_tag": "latest",
                "old_container_id": None,
                "new_container_id": None,
                "health_status": "unknown",
                "rollback_needed": False,
                "attempt": 0,
                "max_attempts": 3,
                "result": None,
                "status": "",
            },
            {"configurable": {"settings": settings}},
        )

    assert result["rollback_needed"] is True
    assert "rollback" in result["result"].lower() or "fail" in result["result"].lower()
    assert result["status"] == "rolled_back"
