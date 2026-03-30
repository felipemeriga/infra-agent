import pytest


def test_settings_loads_required_env_vars(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-guardian-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    from config import Settings

    s = Settings()
    assert s.guardian_url == "http://localhost:3000"
    assert s.guardian_api_key == "test-guardian-key"
    assert s.internal_api_key == "test-internal-key"


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")

    from config import Settings

    s = Settings()
    assert s.mcp_port == 8002
    assert s.compose_dir == "/compose"
    assert s.traefik_api_url == "http://traefik:8080"
    assert s.portainer_url == "http://portainer:9000"
    assert s.portainer_api_key == ""
    assert s.protected_services == ["server-guardian", "traefik", "portainer"]


def test_settings_custom_protected_services(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("PROTECTED_SERVICES", "myapp,traefik")

    from config import Settings

    s = Settings()
    assert s.protected_services == ["myapp", "traefik"]


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("GUARDIAN_URL", raising=False)
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)

    from config import Settings

    with pytest.raises(Exception):
        Settings()
