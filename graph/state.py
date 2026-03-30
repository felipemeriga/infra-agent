from typing import Literal

from typing_extensions import TypedDict


class DiagnoseState(TypedDict):
    service_name: str
    container_status: dict | None
    container_stats: dict | None
    logs: str | None
    traefik_status: dict | None
    compose_config: str | None
    diagnosis: str | None
    recommended_actions: list[str]


class DeployState(TypedDict):
    service_name: str
    image_tag: str
    old_container_id: str | None
    old_container_attrs: dict | None
    new_container_id: str | None
    health_status: Literal["unknown", "healthy", "unhealthy"]
    rollback_needed: bool
    attempt: int
    max_attempts: int
    result: str | None


class RestartState(TypedDict):
    service_name: str
    pre_status: dict | None
    post_status: dict | None
    health_ok: bool
    attempt: int
    max_attempts: int
    result: str | None


class AutoRespondState(TypedDict):
    service_name: str
    trigger: str
    container_status: dict | None
    logs: str | None
    crash_history: dict | None
    llm_decision: str | None
    action_taken: str | None
    action_succeeded: bool
    result: str | None
