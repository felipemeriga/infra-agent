# tests/test_notify.py
import json

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
def test_notify_whatsapp_sends_message(settings):
    route = respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    from notify import notify_whatsapp

    notify_whatsapp("Deploy succeeded for rag-backend", settings=settings)

    assert route.called
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer test-key"
    payload = json.loads(request.read())
    assert payload["message"] == "Deploy succeeded for rag-backend"
    assert payload["number"] == "default"


@respx.mock
def test_notify_whatsapp_does_not_raise_on_failure(settings):
    respx.post("http://guardian:3000/api/notify").mock(
        return_value=httpx.Response(500, text="Server error")
    )

    from notify import notify_whatsapp

    # Should not raise — notifications are best-effort
    notify_whatsapp("test", settings=settings)
