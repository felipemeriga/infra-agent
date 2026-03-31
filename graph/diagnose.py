import json
import logging

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from graph.state import DiagnoseState

logger = logging.getLogger(__name__)


def check_container(state: DiagnoseState, config: RunnableConfig) -> dict:
    """Get container status and stats."""
    import docker
    from docker.errors import NotFound

    name = state["service_name"]
    client = docker.from_env()

    try:
        container = client.containers.get(name)
        status = {
            "state": container.status,
            "image": container.image.tags,
            "started_at": container.attrs.get("State", {}).get("StartedAt", ""),
        }
        stats = container.stats(stream=False)
        mem = stats.get("memory_stats", {})
        container_stats = {
            "memory_usage_mb": round(mem.get("usage", 0) / (1024 * 1024), 1),
            "memory_limit_mb": round(mem.get("limit", 0) / (1024 * 1024), 1),
        }
    except NotFound:
        status = {"state": "not_found", "error": f"Container '{name}' not found"}
        container_stats = {}

    return {"container_status": status, "container_stats": container_stats}


def check_traefik(state: DiagnoseState, config: RunnableConfig) -> dict:
    """Get route and backend health for this service."""
    import httpx

    settings = config.get("configurable", {}).get("settings")
    if settings is None:
        from config import Settings

        settings = Settings()

    name = state["service_name"]
    traefik_info: dict = {"routers": [], "services": []}

    try:
        routers_resp = httpx.get(f"{settings.traefik_api_url}/api/http/routers", timeout=10)
        routers_resp.raise_for_status()
        for r in routers_resp.json():
            if name in r.get("name", "").lower() or name in r.get("service", "").lower():
                traefik_info["routers"].append(r)

        services_resp = httpx.get(f"{settings.traefik_api_url}/api/http/services", timeout=10)
        services_resp.raise_for_status()
        for s in services_resp.json():
            if name in s.get("name", "").lower():
                traefik_info["services"].append(s)
    except Exception as e:
        traefik_info["error"] = str(e)

    return {"traefik_status": traefik_info}


def get_logs(state: DiagnoseState, config: RunnableConfig) -> dict:
    """Fetch recent logs."""
    import docker
    from docker.errors import NotFound

    name = state["service_name"]
    client = docker.from_env()

    try:
        container = client.containers.get(name)
        logs = container.logs(tail=200, timestamps=True)
        return {"logs": logs.decode("utf-8", errors="replace")}
    except NotFound:
        return {"logs": f"Container '{name}' not found — no logs available"}


def read_compose(state: DiagnoseState, config: RunnableConfig) -> dict:
    """Read the compose file for this service."""
    from pathlib import Path

    compose_dir = config.get("configurable", {}).get("compose_dir")
    if compose_dir is None:
        from config import Settings

        compose_dir = Settings().compose_dir

    name = state["service_name"]
    directory = Path(compose_dir)

    if not directory.exists():
        return {"compose_config": "Compose directory not found"}

    for filepath in directory.iterdir():
        if filepath.suffix not in (".yml", ".yaml"):
            continue
        content = filepath.read_text()
        if name in content:
            return {"compose_config": content}

    return {"compose_config": f"No compose file found containing service '{name}'"}


def analyze(state: DiagnoseState, config: RunnableConfig) -> dict:
    """Call server-guardian /api/ask with all collected data for diagnosis."""
    settings = config.get("configurable", {}).get("settings")

    from llm_provider import ask_llm

    prompt = f"""Diagnose the following infrastructure service issue:

Service: {state["service_name"]}
Container Status: {json.dumps(state.get("container_status"), indent=2)}
Container Stats: {json.dumps(state.get("container_stats"), indent=2)}
Traefik Status: {json.dumps(state.get("traefik_status"), indent=2)}
Compose Config: {state.get("compose_config", "N/A")}

Recent Logs:
{state.get("logs", "N/A")}

Provide:
1. A concise diagnosis of what's wrong
2. A list of recommended actions to fix the issue

Format your response as JSON:
{{"diagnosis": "...", "recommended_actions": ["action1", "action2"]}}"""

    response = ""
    try:
        response = ask_llm(
            prompt,
            system=(
                "You are an infrastructure diagnostics expert. "
                "Analyze the provided data and return a JSON diagnosis."
            ),
            settings=settings,
        )
        parsed = json.loads(response)
        return {
            "diagnosis": parsed.get("diagnosis", response),
            "recommended_actions": parsed.get("recommended_actions", []),
        }
    except (json.JSONDecodeError, Exception):
        return {
            "diagnosis": response if response else "Failed to get diagnosis from LLM",
            "recommended_actions": [],
        }


def report(state: DiagnoseState, config: RunnableConfig) -> dict:
    """No-op terminal node — state already contains everything."""
    return {}


def build_diagnose_graph():
    """Build and compile the diagnostic workflow graph."""
    retry = RetryPolicy(max_attempts=3, initial_interval=1.0)
    graph = StateGraph(DiagnoseState)

    graph.add_node("check_container", check_container, retry_policy=retry)
    graph.add_node("check_traefik", check_traefik, retry_policy=retry)
    graph.add_node("get_logs", get_logs, retry_policy=retry)
    graph.add_node("read_compose", read_compose, retry_policy=retry)
    graph.add_node("analyze", analyze, retry_policy=retry)
    graph.add_node("report", report)

    graph.add_edge(START, "check_container")
    graph.add_edge("check_container", "check_traefik")
    graph.add_edge("check_traefik", "get_logs")
    graph.add_edge("get_logs", "read_compose")
    graph.add_edge("read_compose", "analyze")
    graph.add_edge("analyze", "report")
    graph.add_edge("report", END)

    return graph.compile()
