# graph/auto_respond.py
import json
import logging
import time

import docker
import httpx
from docker.errors import NotFound
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from circuit_breaker import CircuitOpenError
from graph.state import AutoRespondState
from llm import ask_llm
from notify import notify_whatsapp

logger = logging.getLogger(__name__)


def _get_settings(config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    if settings is None:
        from config import Settings

        settings = Settings()
    return settings


def _get_throttler(config: RunnableConfig):
    return config.get("configurable", {}).get("throttler")


def _get_circuit_breaker(config: RunnableConfig):
    return config.get("configurable", {}).get("circuit_breaker")


def assess(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Gather container status, logs, and crash history."""
    name = state["service_name"]
    client = docker.from_env()

    try:
        container = client.containers.get(name)
        status = {
            "state": container.status,
            "started_at": container.attrs.get("State", {}).get("StartedAt", ""),
            "finished_at": container.attrs.get("State", {}).get("FinishedAt", ""),
            "restart_count": container.attrs.get("RestartCount", 0),
        }
        logs = container.logs(tail=50, timestamps=True).decode("utf-8", errors="replace")
    except NotFound:
        status = {"state": "not_found", "error": f"Container '{name}' not found"}
        logs = "Container not found — no logs available"

    crash_history = {
        "restart_count": status.get("restart_count", 0),
        "trigger": state["trigger"],
    }

    return {
        "container_status": status,
        "logs": logs,
        "crash_history": crash_history,
    }


def decide(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Ask Claude Code what to do about the detected issue."""
    settings = _get_settings(config)
    circuit_breaker = _get_circuit_breaker(config)

    prompt = f"""An infrastructure issue was detected automatically:

Service: {state["service_name"]}
Trigger: {state["trigger"]}
Container Status: {json.dumps(state.get("container_status"), indent=2)}
Crash History: {json.dumps(state.get("crash_history"), indent=2)}

Recent Logs (last 50 lines):
{state.get("logs", "N/A")}

Based on this information, what should I do?

Respond with JSON only:
{{"decision": "restart" | "escalate" | "wait", "reason": "brief explanation"}}

- "restart": The issue is likely transient, a restart should fix it
- "escalate": The issue requires human intervention, notify the user
- "wait": The issue is not critical, monitor and see if it resolves"""

    system = (
        "You are an infrastructure automation agent. Analyze the issue and "
        "decide the appropriate action. Be conservative — only recommend "
        "restart for transient issues. Escalate anything that looks like a "
        "code bug, data corruption, or configuration error."
    )

    try:
        if circuit_breaker:
            response = circuit_breaker.call(ask_llm, prompt, system=system, settings=settings)
        else:
            response = ask_llm(prompt, system=system, settings=settings)

        parsed = json.loads(response)
        decision = parsed.get("decision", "wait")
        if decision not in ("restart", "escalate", "wait"):
            decision = "wait"
        return {"llm_decision": decision}
    except CircuitOpenError:
        logger.warning("Circuit breaker open — defaulting to wait")
        return {"llm_decision": "wait"}
    except Exception:
        logger.warning("Failed to get LLM decision, defaulting to escalate", exc_info=True)
        return {"llm_decision": "escalate"}


def route_after_decide(state: AutoRespondState) -> str:
    """Route based on LLM decision."""
    decision = state.get("llm_decision", "wait")
    if decision == "restart":
        return "act"
    if decision == "escalate":
        return "report"
    return "end_silent"


def act(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Execute the LLM's decision — restart the container."""
    name = state["service_name"]
    client = docker.from_env()

    try:
        container = client.containers.get(name)
        container.restart(timeout=30)
        return {"action_taken": "restart"}
    except Exception as e:
        logger.error(f"Failed to restart {name}: {e}")
        return {"action_taken": f"restart_failed: {e}"}


def verify(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Health check after action."""
    time.sleep(10)
    settings = _get_settings(config)
    name = state["service_name"]
    client = docker.from_env()

    try:
        container = client.containers.get(name)
        container.reload()
        container_healthy = container.status == "running"
        health = container.attrs.get("State", {}).get("Health", {})
        if health:
            container_healthy = health.get("Status") == "healthy"
    except NotFound:
        return {"action_succeeded": False}

    traefik_ok = False
    try:
        resp = httpx.get(f"{settings.traefik_api_url}/api/http/services", timeout=10)
        resp.raise_for_status()
        for svc in resp.json():
            if name in svc.get("name", "").lower():
                server_status = svc.get("serverStatus", {})
                traefik_ok = any(v == "UP" for v in server_status.values())
                break
    except Exception:
        pass

    succeeded = container_healthy and traefik_ok
    return {"action_succeeded": succeeded}


def route_after_verify(state: AutoRespondState) -> str:
    """Route to silent end or report based on verification."""
    if state["action_succeeded"]:
        return "end_silent"
    return "report"


def report(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Send WhatsApp notification — only reached on escalation or failed action."""
    settings = _get_settings(config)
    throttler = _get_throttler(config)

    event_type = state.get("trigger", "unknown")
    name = state["service_name"]

    if throttler and not throttler.should_notify(name, event_type):
        logger.info(f"Notification throttled for {name}:{event_type}")
        return {"result": f"Throttled: notification suppressed for {name}"}

    decision = state.get("llm_decision", "unknown")
    action = state.get("action_taken")

    if decision == "escalate":
        message = (
            f"ESCALATION: Service '{name}' needs attention.\n"
            f"Trigger: {event_type}\n"
            f"Status: {json.dumps(state.get('container_status', {}))}\n"
            f"Reason: Agent decided to escalate — likely requires manual intervention."
        )
    else:
        message = (
            f"AUTO-RESPONSE FAILED: Service '{name}'\n"
            f"Trigger: {event_type}\n"
            f"Action taken: {action}\n"
            f"Result: Action did not resolve the issue. Manual intervention required."
        )

    notify_whatsapp(message, settings=settings)

    if throttler:
        throttler.record(name, event_type)

    return {"result": message}


def end_silent(state: AutoRespondState, config: RunnableConfig) -> dict:
    """Silent success — no notification needed."""
    action = state.get("action_taken")
    if action:
        logger.info(f"Auto-response succeeded for '{state['service_name']}': {action}")
        return {"result": f"Resolved silently: {action}"}
    return {"result": "No action needed"}


def build_auto_respond_graph(checkpointer=None):
    """Build and compile the autonomous response workflow graph."""
    graph = StateGraph(AutoRespondState)

    graph.add_node("assess", assess)
    graph.add_node("decide", decide)
    graph.add_node("act", act)
    graph.add_node("verify", verify)
    graph.add_node("report", report)
    graph.add_node("end_silent", end_silent)

    graph.add_edge(START, "assess")
    graph.add_edge("assess", "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {"act": "act", "report": "report", "end_silent": "end_silent"},
    )
    graph.add_edge("act", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"end_silent": "end_silent", "report": "report"},
    )
    graph.add_edge("report", END)
    graph.add_edge("end_silent", END)

    return graph.compile(checkpointer=checkpointer)
