from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.config import Settings, get_settings
from backend.main import app


def test_fresh_configuration_is_disabled_without_host() -> None:
    settings = Settings(_env_file=None)

    assert settings.modbus_host is None
    assert settings.collector_enabled is False
    assert settings.public_summary()["host_configured"] is False


def test_collector_cannot_be_enabled_without_host() -> None:
    with pytest.raises(ValidationError, match="MODBUS_HOST is required"):
        Settings(_env_file=None, COLLECTOR_ENABLED=True)


def test_public_configuration_does_not_return_host(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("MODBUS_HOST", "private.example.invalid")
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    try:
        with TestClient(app) as client:
            response = client.get("/api/config")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["host_configured"] is True
    assert "private.example.invalid" not in response.text
    assert "data_dir" not in response.json()


def test_health_endpoint_does_not_require_device_configuration() -> None:
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.get("/api/health")
    get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
