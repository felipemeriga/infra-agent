import json
import logging

import httpx

from config import Settings

logger = logging.getLogger(__name__)


def _get_settings(settings: Settings | None = None) -> Settings:
    return settings if settings is not None else Settings()


def traefik_routers(settings: Settings | None = None) -> str:
    """List all HTTP routers with rules and status."""
    s = _get_settings(settings)
    try:
        response = httpx.get(f"{s.traefik_api_url}/api/http/routers", timeout=10)
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Traefik routers: {e}"})


def traefik_services(settings: Settings | None = None) -> str:
    """List all services with health status."""
    s = _get_settings(settings)
    try:
        response = httpx.get(f"{s.traefik_api_url}/api/http/services", timeout=10)
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Traefik services: {e}"})


def traefik_entrypoints(settings: Settings | None = None) -> str:
    """List entrypoints (ports, protocols)."""
    s = _get_settings(settings)
    try:
        response = httpx.get(f"{s.traefik_api_url}/api/entrypoints", timeout=10)
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Traefik entrypoints: {e}"})
