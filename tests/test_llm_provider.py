from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from config import Settings


@pytest.fixture()
def settings_no_fallback(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://guardian:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-key")
    return Settings()


@pytest.fixture()
def settings_with_fallback(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://guardian:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-20250514")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    return Settings()


@respx.mock
def test_primary_succeeds_no_fallback_called(settings_no_fallback):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(200, json={"response": "diagnosis result"})
    )

    from llm_provider import ask_llm

    result = ask_llm("test prompt", settings=settings_no_fallback)
    assert result == "diagnosis result"


@respx.mock
def test_primary_fails_no_fallback_raises(settings_no_fallback):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    from llm_provider import ask_llm

    with pytest.raises(Exception):
        ask_llm("test prompt", settings=settings_no_fallback)


@respx.mock
def test_primary_fails_fallback_succeeds(settings_with_fallback):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="fallback result")

    from llm_provider import ask_llm

    with patch("llm_provider._get_direct_llm", return_value=mock_llm):
        result = ask_llm("test prompt", settings=settings_with_fallback)

    assert result == "fallback result"
    mock_llm.invoke.assert_called_once()


@respx.mock
def test_primary_fails_fallback_fails_raises(settings_with_fallback):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("LLM API error")

    from llm_provider import ask_llm

    with patch("llm_provider._get_direct_llm", return_value=mock_llm):
        with pytest.raises(Exception, match="LLM API error"):
            ask_llm("test prompt", settings=settings_with_fallback)


@respx.mock
def test_primary_succeeds_fallback_not_attempted(settings_with_fallback):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(200, json={"response": "guardian result"})
    )

    from llm_provider import ask_llm

    with patch("llm_provider._get_direct_llm") as mock_get_llm:
        result = ask_llm("test prompt", settings=settings_with_fallback)

    assert result == "guardian result"
    mock_get_llm.assert_not_called()
