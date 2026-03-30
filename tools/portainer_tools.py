import json
import logging

import httpx

from config import Settings

logger = logging.getLogger(__name__)


def _get_settings(settings: Settings | None = None) -> Settings:
    return settings if settings is not None else Settings()


def _portainer_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.portainer_api_key:
        headers["X-API-Key"] = settings.portainer_api_key
    return headers


def portainer_stacks(settings: Settings | None = None) -> str:
    """List all Portainer stacks with status."""
    s = _get_settings(settings)
    try:
        response = httpx.get(
            f"{s.portainer_url}/api/stacks",
            headers=_portainer_headers(s),
            timeout=10,
        )
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Portainer stacks: {e}"})


def portainer_endpoints(settings: Settings | None = None) -> str:
    """List managed Docker endpoints."""
    s = _get_settings(settings)
    try:
        response = httpx.get(
            f"{s.portainer_url}/api/endpoints",
            headers=_portainer_headers(s),
            timeout=10,
        )
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Portainer endpoints: {e}"})
