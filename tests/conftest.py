from unittest.mock import MagicMock, patch

import pytest

from config import Settings


@pytest.fixture()
def settings(monkeypatch):
    monkeypatch.setenv("GUARDIAN_URL", "http://guardian:3000")
    monkeypatch.setenv("GUARDIAN_API_KEY", "test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-key")
    return Settings()


@pytest.fixture()
def mock_docker_client():
    with patch("docker.from_env") as mock_from_env:
        client = MagicMock()
        mock_from_env.return_value = client
        yield client
