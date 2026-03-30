# mcp_server.py
import asyncio
import json
import logging

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier

from config import Settings
from graph.deploy import build_deploy_graph
from graph.diagnose import build_diagnose_graph
from graph.restart import build_restart_graph
from monitor import health_monitor
from throttler import NotificationThrottler
from tools.compose_tools import list_compose_files, read_compose_file, search_compose_files
from tools.docker_tools import (
    container_inspect,
    container_logs,
    container_stats,
    list_containers,
    list_images,
)
from tools.portainer_tools import portainer_endpoints, portainer_stacks
from tools.traefik_tools import traefik_entrypoints, traefik_routers, traefik_services
from watcher import ExpectedStopTracker, docker_event_watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()


class BearerTokenAuth(TokenVerifier):
    """Simple bearer token auth that validates against a known secret."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if token == self._token:
            return AccessToken(token=token, client_id="infra-agent", scopes=[])
        return None


auth = BearerTokenAuth(token=settings.internal_api_key)
mcp = FastMCP("Infrastructure Agent", auth=auth)

# --- Background Tasks ---

throttler = NotificationThrottler(cooldown=settings.notification_cooldown)
expected_stops = ExpectedStopTracker()


@mcp.tool()
def get_agent_status() -> str:
    """Get the status of the infra-agent's proactive monitoring systems."""
    return json.dumps(
        {
            "event_watcher": "running",
            "health_monitor": "running",
            "monitor_interval": settings.monitor_interval,
            "notification_cooldown": settings.notification_cooldown,
            "memory_threshold_pct": settings.memory_threshold_pct,
        },
        indent=2,
    )


# --- Granular Docker Tools ---


@mcp.tool()
def mcp_list_containers() -> str:
    """List all Docker containers with status, image, ports, and uptime."""
    return list_containers()


@mcp.tool()
def mcp_container_logs(name: str, lines: int = 100) -> str:
    """Get recent logs from a Docker container."""
    return container_logs(name, lines=lines)


@mcp.tool()
def mcp_container_stats(name: str) -> str:
    """Get CPU, memory, and network I/O snapshot for a Docker container."""
    return container_stats(name)


@mcp.tool()
def mcp_container_inspect(name: str) -> str:
    """Get full container configuration (env, mounts, network, restart policy)."""
    return container_inspect(name)


@mcp.tool()
def mcp_list_images() -> str:
    """List all Docker images with tags and sizes."""
    return list_images()


# --- Granular Traefik Tools ---


@mcp.tool()
def mcp_traefik_routers() -> str:
    """List all Traefik HTTP routers with rules and status."""
    return traefik_routers(settings=settings)


@mcp.tool()
def mcp_traefik_services() -> str:
    """List all Traefik services with health status."""
    return traefik_services(settings=settings)


@mcp.tool()
def mcp_traefik_entrypoints() -> str:
    """List Traefik entrypoints (ports, protocols)."""
    return traefik_entrypoints(settings=settings)


# --- Granular Portainer Tools ---


@mcp.tool()
def mcp_portainer_stacks() -> str:
    """List all Portainer stacks with status."""
    return portainer_stacks(settings=settings)


@mcp.tool()
def mcp_portainer_endpoints() -> str:
    """List managed Portainer Docker endpoints."""
    return portainer_endpoints(settings=settings)


# --- Granular Compose Tools ---


@mcp.tool()
def mcp_list_compose_files() -> str:
    """List all compose files (.yml/.yaml) in the compose directory."""
    return list_compose_files()


@mcp.tool()
def mcp_read_compose_file(filename: str) -> str:
    """Read and return the content of a compose file."""
    return read_compose_file(filename)


@mcp.tool()
def mcp_search_compose_files(query: str) -> str:
    """Search across all compose files for a service name, image, or config value."""
    return search_compose_files(query)


# --- Workflow Tools (LangGraph) ---


@mcp.tool()
def diagnose_service(name: str) -> str:
    """Run a full diagnostic workflow for a service.

    Collects container status, logs, Traefik health, and compose config,
    then uses LLM to analyze and diagnose issues.
    """
    graph = build_diagnose_graph()
    result = graph.invoke(
        {
            "service_name": name,
            "container_status": None,
            "container_stats": None,
            "logs": None,
            "traefik_status": None,
            "compose_config": None,
            "diagnosis": None,
            "recommended_actions": [],
        },
        {"configurable": {"settings": settings}},
    )
    return json.dumps(
        {
            "service": result["service_name"],
            "status": result.get("container_status", {}).get("state", "unknown"),
            "diagnosis": result.get("diagnosis", "No diagnosis"),
            "container": result.get("container_status"),
            "stats": result.get("container_stats"),
            "traefik": result.get("traefik_status"),
            "recommended_actions": result.get("recommended_actions", []),
        },
        indent=2,
    )


@mcp.tool()
def deploy_service(name: str, image_tag: str = "latest") -> str:
    """Deploy a service with a new image tag.

    Pulls the image, stops the old container, starts a new one with the same config,
    health checks, and rolls back on failure.
    """
    graph = build_deploy_graph()
    result = graph.invoke(
        {
            "service_name": name,
            "image_tag": image_tag,
            "old_container_id": None,
            "old_container_attrs": None,
            "new_container_id": None,
            "health_status": "unknown",
            "rollback_needed": False,
            "attempt": 0,
            "max_attempts": 3,
            "result": None,
        },
        {"configurable": {"settings": settings}},
    )
    return result.get("result", "Deploy completed with unknown status")


@mcp.tool()
def restart_service(name: str) -> str:
    """Restart a service container with health checking and automatic escalation on failure."""
    graph = build_restart_graph()
    result = graph.invoke(
        {
            "service_name": name,
            "pre_status": None,
            "post_status": None,
            "health_ok": False,
            "attempt": 0,
            "max_attempts": 3,
            "result": None,
        },
        {"configurable": {"settings": settings}},
    )
    return result.get("result", "Restart completed with unknown status")


async def start_background_tasks():
    """Start the proactive monitoring background tasks."""
    logger.info("Starting background monitoring tasks")
    asyncio.create_task(docker_event_watcher(settings, throttler, expected_stops))
    asyncio.create_task(health_monitor(settings, throttler))


if __name__ == "__main__":
    logger.info(f"Starting Infrastructure Agent MCP server on port {settings.mcp_port}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_background_tasks())

    mcp.run(transport="sse", host="0.0.0.0", port=settings.mcp_port)
