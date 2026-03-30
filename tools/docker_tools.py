import json
import logging

import docker
from docker.errors import NotFound

logger = logging.getLogger(__name__)


def _get_client() -> docker.DockerClient:
    return docker.from_env()


def list_containers() -> str:
    """List all containers with status, image, ports, and uptime."""
    client = _get_client()
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        ports = c.attrs.get("NetworkSettings", {}).get("Ports", {})
        started_at = c.attrs.get("State", {}).get("StartedAt", "")
        result.append(
            {
                "name": c.name,
                "status": c.status,
                "image": c.image.tags,
                "ports": ports,
                "started_at": started_at,
            }
        )
    return json.dumps(result, indent=2)


def container_logs(name: str, lines: int = 100) -> str:
    """Get recent logs from a container."""
    client = _get_client()
    try:
        container = client.containers.get(name)
        logs = container.logs(tail=lines, timestamps=True)
        return logs.decode("utf-8", errors="replace")
    except NotFound:
        return json.dumps({"error": f"Container '{name}' not found"})


def container_stats(name: str) -> str:
    """Get CPU, memory, and network I/O snapshot for a container."""
    client = _get_client()
    try:
        container = client.containers.get(name)
        stats = container.stats(stream=False)
        return json.dumps(stats, indent=2)
    except NotFound:
        return json.dumps({"error": f"Container '{name}' not found"})


def container_inspect(name: str) -> str:
    """Get full container configuration (env, mounts, network, restart policy)."""
    client = _get_client()
    try:
        container = client.containers.get(name)
        return json.dumps(container.attrs, indent=2)
    except NotFound:
        return json.dumps({"error": f"Container '{name}' not found"})


def list_images() -> str:
    """List all images with tags and sizes."""
    client = _get_client()
    images = client.images.list()
    result = []
    for img in images:
        result.append(
            {
                "id": img.short_id,
                "tags": img.tags,
                "size_mb": round(img.attrs.get("Size", 0) / (1024 * 1024), 1),
            }
        )
    return json.dumps(result, indent=2)
