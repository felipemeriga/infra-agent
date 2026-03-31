import logging
import time
from typing import Literal

import docker
import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from graph.state import RestartState
from notify import notify_whatsapp

logger = logging.getLogger(__name__)


def _get_settings(config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    if settings is None:
        from config import Settings

        settings = Settings()
    return settings


def pre_check(state: RestartState, config: RunnableConfig) -> dict:
    """Check if service is protected and capture pre-restart status."""
    settings = _get_settings(config)
    name = state["service_name"]

    if name in settings.protected_services:
        return {"result": f"Refused: '{name}' is a protected service."}

    client = docker.from_env()
    try:
        container = client.containers.get(name)
        pre_status = {
            "status": container.status,
            "id": container.id,
        }
    except docker.errors.NotFound:
        pre_status = {"status": "not_found"}

    return {"pre_status": pre_status}


def _route_pre_check(state: RestartState) -> Literal["restart", "end_early"]:
    if state.get("result") is not None:
        return "end_early"
    return "restart"


def restart(state: RestartState, config: RunnableConfig) -> dict:
    """Restart the container."""
    client = docker.from_env()
    container = client.containers.get(state["service_name"])
    container.restart(timeout=30)
    return {}


def wait(state: RestartState, config: RunnableConfig) -> dict:
    """Wait for container to stabilize."""
    time.sleep(10)
    return {}


def health_check(state: RestartState, config: RunnableConfig) -> dict:
    """Check container and Traefik health after restart."""
    settings = _get_settings(config)
    name = state["service_name"]

    client = docker.from_env()
    container = client.containers.get(name)
    container.reload() if hasattr(container, "reload") else None

    health = container.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")

    traefik_ok = False
    try:
        resp = httpx.get(f"{settings.traefik_api_url}/api/http/services", timeout=10)
        resp.raise_for_status()
        for svc in resp.json():
            if name in svc.get("name", "").lower():
                server_status = svc.get("serverStatus", {})
                if any(v == "UP" for v in server_status.values()):
                    traefik_ok = True
                    break
    except Exception:
        logger.warning("Traefik health check failed", exc_info=True)

    healthy = health == "healthy" and traefik_ok
    post_status = {"health": health, "traefik_ok": traefik_ok}

    update: dict = {"health_ok": healthy, "post_status": post_status}
    if not healthy:
        update["attempt"] = state["attempt"] + 1
    return update


def _route_health_check(state: RestartState) -> Literal["success", "wait", "escalate"]:
    if state["health_ok"]:
        return "success"
    if state["attempt"] < state["max_attempts"]:
        return "wait"
    return "escalate"


def success(state: RestartState, config: RunnableConfig) -> dict:
    """Report successful restart and notify."""
    settings = _get_settings(config)
    name = state["service_name"]
    message = f"Service '{name}' restarted successfully."
    notify_whatsapp(message, settings=settings)
    return {"result": message}


def escalate(state: RestartState, config: RunnableConfig) -> dict:
    """Escalate after max attempts exhausted."""
    settings = _get_settings(config)
    name = state["service_name"]
    attempts = state["attempt"]
    message = f"Restart failed for '{name}' after {attempts} attempts. Escalating."
    notify_whatsapp(message, settings=settings)
    return {"result": message}


def end_early(state: RestartState, config: RunnableConfig) -> dict:
    """Terminal node for protected services."""
    return {}


def build_restart_graph():
    """Build and compile the restart workflow graph."""
    retry = RetryPolicy(max_attempts=3, initial_interval=1.0)
    graph = StateGraph(RestartState)

    graph.add_node("pre_check", pre_check, retry_policy=retry)
    graph.add_node("restart", restart, retry_policy=retry)
    graph.add_node("wait", wait)
    graph.add_node("health_check", health_check, retry_policy=retry)
    graph.add_node("success", success)
    graph.add_node("escalate", escalate)
    graph.add_node("end_early", end_early)

    graph.add_edge(START, "pre_check")
    graph.add_conditional_edges(
        "pre_check",
        _route_pre_check,
        {"restart": "restart", "end_early": "end_early"},
    )
    graph.add_edge("restart", "wait")
    graph.add_edge("wait", "health_check")
    graph.add_conditional_edges(
        "health_check",
        _route_health_check,
        {"success": "success", "wait": "wait", "escalate": "escalate"},
    )
    graph.add_edge("success", END)
    graph.add_edge("escalate", END)
    graph.add_edge("end_early", END)

    return graph.compile()
