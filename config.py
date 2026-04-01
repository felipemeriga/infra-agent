import json
from typing import Any

from pydantic_settings import BaseSettings, EnvSettingsSource


class CustomEnvSettingsSource(EnvSettingsSource):
    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        """Override to handle comma-separated lists before falling back to JSON."""
        if field_name == "protected_services" and isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return [item.strip() for item in value.split(",") if item.strip()]
        return super().decode_complex_value(field_name, field, value)


class Settings(BaseSettings):
    guardian_url: str
    guardian_api_key: str
    internal_api_key: str
    mcp_port: int = 8002
    compose_dir: str = "/compose"
    traefik_api_url: str = "http://traefik:8080"
    protected_services: list[str] = ["server-guardian", "traefik"]

    # Monitoring
    monitor_interval: int = 60
    notification_cooldown: int = 900
    memory_threshold_pct: int = 90
    max_restarts_window: int = 600
    max_restarts_count: int = 3
    strike_threshold: int = 2

    # Production hardening
    supabase_db_url: str = ""
    circuit_breaker_failures: int = 3
    circuit_breaker_timeout: int = 60
    shutdown_timeout: int = 30

    # LLM fallback
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (
            init_settings,
            CustomEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )
