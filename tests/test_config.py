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
    assert s.protected_services == ["server-guardian"]


def test_settings_custom_protected_services(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("PROTECTED_SERVICES", "myapp,database")

    from config import Settings

    s = Settings()
    assert s.protected_services == ["myapp", "database"]


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("GUARDIAN_URL", raising=False)
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)

    from config import Settings

    with pytest.raises(Exception):
        Settings()


def test_settings_monitoring_defaults(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")

    from config import Settings

    s = Settings()
    assert s.monitor_interval == 60
    assert s.notification_cooldown == 900
    assert s.memory_threshold_pct == 90
    assert s.max_restarts_window == 600
    assert s.max_restarts_count == 3
    assert s.strike_threshold == 2


def test_settings_custom_monitoring(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("MONITOR_INTERVAL", "30")
    monkeypatch.setenv("MEMORY_THRESHOLD_PCT", "85")

    from config import Settings

    s = Settings()
    assert s.monitor_interval == 30
    assert s.memory_threshold_pct == 85


def test_settings_hardening_defaults(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")

    from config import Settings

    s = Settings()
    assert s.supabase_db_url == ""
    assert s.circuit_breaker_failures == 3
    assert s.circuit_breaker_timeout == 60
    assert s.shutdown_timeout == 30


def test_settings_custom_hardening(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://localhost:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "key")
    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pass@host:5432/db")
    monkeypatch.setenv("CIRCUIT_BREAKER_FAILURES", "5")
    monkeypatch.setenv("SHUTDOWN_TIMEOUT", "45")

    from config import Settings

    s = Settings()
    assert s.supabase_db_url == "postgresql://user:pass@host:5432/db"
    assert s.circuit_breaker_failures == 5
    assert s.shutdown_timeout == 45
