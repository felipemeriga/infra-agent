import httpx
import pytest
import respx

from config import Settings


@pytest.fixture()
def settings(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://guardian:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-key")
    return Settings()


@respx.mock
def test_ask_guardian_sends_prompt_and_returns_response(settings):
    route = respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(200, json={"response": "The container is healthy."})
    )

    from llm import ask_guardian

    result = ask_guardian("What is the status?", settings=settings)
    assert result == "The container is healthy."
    assert route.called
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer test-key"
    body = request.read()
    import json

    payload = json.loads(body)
    assert payload["prompt"] == "What is the status?"


@respx.mock
def test_ask_guardian_with_system_prompt(settings):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(200, json={"response": "OK"})
    )

    from llm import ask_guardian

    result = ask_guardian("Check logs", system="You are a diagnostics expert.", settings=settings)
    assert result == "OK"


@respx.mock
def test_ask_guardian_raises_on_http_error(settings):
    respx.post("http://guardian:3000/api/ask").mock(
        return_value=httpx.Response(500, text="Internal error")
    )

    from llm import ask_guardian

    with pytest.raises(httpx.HTTPStatusError):
        ask_guardian("fail", settings=settings)
