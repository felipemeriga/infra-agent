import httpx

from config import Settings


def ask_llm(
    prompt: str,
    system: str | None = None,
    timeout: int = 120000,
    settings: Settings | None = None,
) -> str:
    """Send a prompt to server-guardian's Claude Code instance for reasoning."""
    if settings is None:
        settings = Settings()

    response = httpx.post(
        f"{settings.guardian_url}/api/ask",
        json={"prompt": prompt, "system": system, "timeout": timeout},
        headers={"Authorization": f"Bearer {settings.guardian_api_key}"},
        timeout=timeout / 1000 + 10,
    )
    response.raise_for_status()
    return response.json()["response"]
