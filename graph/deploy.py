import logging
import time
from typing import Literal

import docker
import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from graph.state import DeployState
from notify import notify_whatsapp

logger = logging.getLogger(__name__)


def _get_settings(config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    if settings is None:
        from config import Settings

        settings = Settings()
    return settings


def pull_image(state: DeployState, config: RunnableConfig) -> dict:
    """Check protected services, then pull the new image and save old container info."""
    settings = _get_settings(config)
    name = state["service_name"]

    if name in settings.protected_services:
        return {"result": f"Refused: '{name}' is a protected service.", "status": "error"}

    client = docker.from_env()
    container = client.containers.get(name)
    current_image = container.attrs["Config"]["Image"]
    repo = current_image.rsplit(":", 1)[0]

    tag = state["image_tag"]
    client.images.pull(repo, tag=tag)

    # Save old container info for reconstruction after removal
    return {
        "old_container_id": container.id,
        "old_container_attrs": container.attrs,
        "status": "pulling",
    }


def _route_pull_image(state: DeployState) -> Literal["pre_check", "end_early"]:
    if state.get("result") is not None:
        return "end_early"
    return "pre_check"


def pre_check(state: DeployState, config: RunnableConfig) -> dict:
    """Validate old container info is saved before proceeding."""
    return {"status": "pre_check"}


def stop_old(state: DeployState, config: RunnableConfig) -> dict:
    """Stop and remove the old container using low-level API."""
    client = docker.from_env()
    old_id = state["old_container_id"]
    client.api.stop(old_id, timeout=30)
    client.api.remove_container(old_id)
    return {"status": "deploying"}


def start_new(state: DeployState, config: RunnableConfig) -> dict:
    """Start a new container using saved attrs from the old one."""
    client = docker.from_env()
    attrs = state["old_container_attrs"]
    name = state["service_name"]
    tag = state["image_tag"]

    config_section = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})

    # Build image reference
    current_image = config_section.get("Image", "")
    repo = current_image.rsplit(":", 1)[0]
    image = f"{repo}:{tag}"

    # Extract environment
    environment = config_section.get("Env", [])

    # Extract labels
    labels = config_section.get("Labels", {})

    # Extract port bindings
    port_bindings = host_config.get("PortBindings", {})
    ports = {}
    for container_port, host_ports in port_bindings.items():
        if host_ports:
            ports[container_port] = int(host_ports[0]["HostPort"])

    # Extract volumes
    volumes = host_config.get("Binds", [])

    # Extract restart policy
    restart_raw = host_config.get("RestartPolicy", {})
    restart_policy = {
        "Name": restart_raw.get("Name", "no"),
        "MaximumRetryCount": restart_raw.get("MaximumRetryCount", 0),
    }

    # Extract network
    network_mode = host_config.get("NetworkMode", "bridge")

    new_container = client.containers.run(
        image,
        name=name,
        environment=environment,
        ports=ports,
        volumes=volumes,
        restart_policy=restart_policy,
        network=network_mode,
        labels=labels,
        detach=True,
    )

    return {"new_container_id": new_container.id, "status": "deploying"}


def health_check(state: DeployState, config: RunnableConfig) -> dict:
    """Check container health and Traefik status."""
    settings = _get_settings(config)
    name = state["service_name"]

    time.sleep(10)

    client = docker.from_env()
    container = client.containers.get(name)

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
    health_status = "healthy" if healthy else "unhealthy"

    update: dict = {
        "health_status": health_status,
        "attempt": state["attempt"] + 1,
        "status": "verifying",
    }

    return update


def _route_health_check(
    state: DeployState,
) -> Literal["verify", "health_check", "rollback"]:
    if state["health_status"] == "healthy":
        return "verify"
    if state["attempt"] < state["max_attempts"]:
        return "health_check"
    return "rollback"


def verify(state: DeployState, config: RunnableConfig) -> dict:
    """Verify health status."""
    return {"status": "verifying"}


def _route_verify(state: DeployState) -> Literal["success", "rollback"]:
    if state["health_status"] == "healthy":
        return "success"
    return "rollback"


def success(state: DeployState, config: RunnableConfig) -> dict:
    """Report successful deploy and notify."""
    settings = _get_settings(config)
    name = state["service_name"]
    tag = state["image_tag"]
    message = f"Deploy success: '{name}' updated to tag '{tag}'."
    notify_whatsapp(message, settings=settings)
    return {"result": message, "status": "success"}


def rollback(state: DeployState, config: RunnableConfig) -> dict:
    """Roll back to old container on failure."""
    settings = _get_settings(config)
    name = state["service_name"]
    client = docker.from_env()

    # Try to stop and remove the new container
    try:
        new_container = client.containers.get(name)
        new_container.stop(timeout=10)
        new_container.remove()
    except Exception:
        logger.warning("Failed to remove new container during rollback", exc_info=True)

    # Try to restart old container by ID
    old_id = state.get("old_container_id")
    if old_id:
        try:
            old_container = client.containers.get(old_id)
            old_container.start()
        except Exception:
            logger.warning("Failed to restart old container during rollback", exc_info=True)

    message = f"Deploy rollback: '{name}' deployment failed, rolled back."
    notify_whatsapp(message, settings=settings)
    return {"rollback_needed": True, "result": message, "status": "rolled_back"}


def end_early(state: DeployState, config: RunnableConfig) -> dict:
    """Terminal node for protected services."""
    return {"status": "error"}


def build_deploy_graph(checkpointer=None):
    """Build and compile the deploy workflow graph."""
    retry = RetryPolicy(max_attempts=3, initial_interval=1.0)
    graph = StateGraph(DeployState)

    graph.add_node("pull_image", pull_image, retry_policy=retry)
    graph.add_node("pre_check", pre_check, retry_policy=retry)
    graph.add_node("stop_old", stop_old, retry_policy=retry)
    graph.add_node("start_new", start_new, retry_policy=retry)
    graph.add_node("health_check", health_check, retry_policy=retry)
    graph.add_node("verify", verify, retry_policy=retry)
    graph.add_node("success", success)
    graph.add_node("rollback", rollback)
    graph.add_node("end_early", end_early)

    graph.add_edge(START, "pull_image")
    graph.add_conditional_edges(
        "pull_image",
        _route_pull_image,
        {"pre_check": "pre_check", "end_early": "end_early"},
    )
    graph.add_edge("pre_check", "stop_old")
    graph.add_edge("stop_old", "start_new")
    graph.add_edge("start_new", "health_check")
    graph.add_conditional_edges(
        "health_check",
        _route_health_check,
        {"verify": "verify", "health_check": "health_check", "rollback": "rollback"},
    )
    graph.add_conditional_edges(
        "verify",
        _route_verify,
        {"success": "success", "rollback": "rollback"},
    )
    graph.add_edge("success", END)
    graph.add_edge("rollback", END)
    graph.add_edge("end_early", END)

    return graph.compile(checkpointer=checkpointer)
