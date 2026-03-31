import importlib
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from config import Settings
from llm import ask_guardian

logger = logging.getLogger(__name__)

_PROVIDERS = {
    "anthropic": ("langchain_anthropic", "ChatAnthropic"),
    "openai": ("langchain_openai", "ChatOpenAI"),
    "google": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
}

_direct_llm_cache = {}


def _get_direct_llm(settings: Settings):
    """Get or create a direct LLM instance based on settings."""
    cache_key = f"{settings.llm_provider}:{settings.llm_model}"
    if cache_key in _direct_llm_cache:
        return _direct_llm_cache[cache_key]

    provider = settings.llm_provider
    if provider not in _PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported: {list(_PROVIDERS)}")

    module_name, class_name = _PROVIDERS[provider]
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    llm = cls(model=settings.llm_model, api_key=settings.llm_api_key)
    _direct_llm_cache[cache_key] = llm
    return llm


def ask_llm(
    prompt: str,
    system: str | None = None,
    timeout: int = 120000,
    settings: Settings | None = None,
) -> str:
    """Send a prompt to server-guardian (primary) or direct LLM (fallback).

    Tries server-guardian first. If it fails and a direct LLM provider is
    configured, falls back to calling the LLM directly.
    """
    if settings is None:
        settings = Settings()

    # Primary: server-guardian
    try:
        return ask_guardian(prompt, system=system, timeout=timeout, settings=settings)
    except Exception as primary_err:
        if not settings.llm_provider:
            raise

        logger.warning(f"Server-guardian failed, falling back to direct LLM: {primary_err}")

    # Fallback: direct LLM
    llm = _get_direct_llm(settings)
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    response = llm.invoke(messages)
    return response.content
