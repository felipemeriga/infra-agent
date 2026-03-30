import json
from unittest.mock import MagicMock


def test_list_containers_returns_all_containers(mock_docker_client):
    container1 = MagicMock()
    container1.name = "web-app"
    container1.status = "running"
    container1.image.tags = ["nginx:latest"]
    container1.attrs = {
        "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "8080"}]}},
        "State": {"StartedAt": "2026-03-30T10:00:00Z"},
    }

    container2 = MagicMock()
    container2.name = "redis"
    container2.status = "exited"
    container2.image.tags = ["redis:alpine"]
    container2.attrs = {
        "NetworkSettings": {"Ports": {}},
        "State": {"StartedAt": "2026-03-29T08:00:00Z"},
    }

    mock_docker_client.containers.list.return_value = [container1, container2]

    from tools.docker_tools import list_containers

    result = json.loads(list_containers())
    assert len(result) == 2
    assert result[0]["name"] == "web-app"
    assert result[0]["status"] == "running"
    assert result[1]["name"] == "redis"
    assert result[1]["status"] == "exited"


def test_container_logs_returns_tail_lines(mock_docker_client):
    container = MagicMock()
    container.logs.return_value = b"line1\nline2\nline3"
    mock_docker_client.containers.get.return_value = container

    from tools.docker_tools import container_logs

    result = container_logs("web-app", lines=50)
    assert "line1" in result
    assert "line3" in result
    container.logs.assert_called_once_with(tail=50, timestamps=True)


def test_container_stats_returns_snapshot(mock_docker_client):
    container = MagicMock()
    container.stats.return_value = {
        "cpu_stats": {"cpu_usage": {"total_usage": 100000}},
        "precpu_stats": {"cpu_usage": {"total_usage": 90000}},
        "memory_stats": {"usage": 52428800, "limit": 268435456},
        "networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 2048}},
    }
    mock_docker_client.containers.get.return_value = container

    from tools.docker_tools import container_stats

    result = json.loads(container_stats("web-app"))
    assert "cpu_stats" in result
    assert "memory_stats" in result


def test_container_inspect_returns_full_config(mock_docker_client):
    container = MagicMock()
    container.attrs = {
        "Config": {"Image": "nginx:latest", "Env": ["PORT=80"]},
        "HostConfig": {"RestartPolicy": {"Name": "always"}},
        "NetworkSettings": {"Networks": {"bridge": {}}},
        "Mounts": [],
    }
    mock_docker_client.containers.get.return_value = container

    from tools.docker_tools import container_inspect

    result = json.loads(container_inspect("web-app"))
    assert result["Config"]["Image"] == "nginx:latest"


def test_list_images_returns_all_images(mock_docker_client):
    image1 = MagicMock()
    image1.tags = ["nginx:latest"]
    image1.short_id = "sha256:abc123"
    image1.attrs = {"Size": 142000000}

    image2 = MagicMock()
    image2.tags = ["redis:alpine"]
    image2.short_id = "sha256:def456"
    image2.attrs = {"Size": 32000000}

    mock_docker_client.images.list.return_value = [image1, image2]

    from tools.docker_tools import list_images

    result = json.loads(list_images())
    assert len(result) == 2
    assert result[0]["tags"] == ["nginx:latest"]


def test_container_logs_not_found(mock_docker_client):
    from docker.errors import NotFound

    mock_docker_client.containers.get.side_effect = NotFound("not found")

    from tools.docker_tools import container_logs

    result = container_logs("nonexistent")
    assert "not found" in result.lower() or "error" in result.lower()
