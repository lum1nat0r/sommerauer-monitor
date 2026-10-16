import time

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.config import Settings, get_settings
from backend.main import app
from backend.modbus import RegisterRead
from backend.storage import StorageError


MUTATION_HEADERS = {
    "Origin": "http://testserver",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "SommerauerMonitor",
}

@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.setenv("MODBUS_HOST", "")
    monkeypatch.setenv("MODBUS_PORT", "1502")
    monkeypatch.setenv("MODBUS_UNIT_ID", "255")
    monkeypatch.setenv("COLLECTOR_MAX_REQUESTS", "")
    monkeypatch.setenv("REGISTER_PROFILE", "core")
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Europe/Vienna")
    monkeypatch.setenv("PUBLIC_ORIGIN", "")
    monkeypatch.setattr("backend.main.get_settings", lambda: Settings(_env_file=None))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

def test_fresh_configuration_is_disabled_without_host() -> None:
    settings = Settings(_env_file=None)

    assert settings.modbus_host is None
    assert settings.collector_enabled is False
    assert settings.public_summary()["host_configured"] is False


def test_collector_cannot_be_enabled_without_host() -> None:
    with pytest.raises(ValidationError, match="MODBUS_HOST is required"):
        Settings(_env_file=None, COLLECTOR_ENABLED=True)

def test_finite_collector_limit_is_configurable() -> None:
    settings = Settings(
        _env_file=None,
        COLLECTOR_ENABLED=True,
        MODBUS_HOST="heater.invalid",
        COLLECTOR_MAX_REQUESTS=3,
    )

    assert settings.collector_max_requests == 3


def test_app_stops_after_configured_request_limit_and_stores_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "heater.invalid")
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    monkeypatch.setenv("COLLECTOR_MAX_REQUESTS", "1")
    reads = []

    class FakeClient:
        def __init__(self, host, port):
            pass

        def read(self, block):
            reads.append(block.offset)
            return RegisterRead(block.offset, (42,))

    monkeypatch.setattr("backend.collector.ModbusTcpClient", FakeClient)
    get_settings.cache_clear()
    with TestClient(app) as client:
        deadline = time.monotonic() + 2
        while client.get("/api/collector/status").json()["state"] != "completed":
            if time.monotonic() >= deadline:
                pytest.fail("finite collector did not complete")
            time.sleep(0.01)
        history = client.get("/api/history/boiler.temperature").json()

    assert reads == [4102]
    assert history["total"] == 1
    assert history["items"][0]["value"] == 42

    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    get_settings.cache_clear()
    with TestClient(app) as client:
        status = client.get("/api/collector/status").json()
        health = client.get("/api/health").json()
        restored_history = client.get("/api/history/boiler.temperature").json()

    assert status["state"] == "completed"
    assert status["reason"] is None
    assert health == {"status": "ok", "database": "ok"}
    assert restored_history == history
    assert reads == [4102]


def test_configuration_rejects_unimplemented_register_profiles() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, REGISTER_PROFILE="all")

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

    assert response.json() == {"status": "ok", "database": "ok"}

def test_version_endpoint_reports_build_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("BUILD_REVISION", "synthetic-revision")

    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"version": "0.1.0", "revision": "synthetic-revision"}


def test_collector_status_reports_saved_runtime_state_without_configuration_fingerprint() -> None:
    with TestClient(app) as client:
        app.state.storage.save_collector_state(
            {
                "state": "reconnect_wait",
                "error": "synthetic connection error",
                "reconnect_attempts": 2,
                "retry_at": "2026-10-14T00:02:00+00:00",
                "next_action": "Retry same core block",
                "profile_id": "core",
                "configuration_id": "private fingerprint",
            },
            "2026-10-14T00:00:00+00:00",
        )
        response = client.get("/api/collector/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "reconnect_wait",
        "reason": "Verbindungsfehler; begrenzte Wiederaufnahme geplant",
        "reconnect_attempts": 2,
        "reconnect_attempt_limit": 5,
        "next_action_at": "2026-10-14T00:02:00+00:00",
        "next_action": "Retry same core block",
        "profile_id": "core",
    }
    assert "private fingerprint" not in response.text


def test_collector_status_survives_unreadable_state_without_exposing_storage_details() -> None:
    with TestClient(app) as client:
        def unreadable_state():
            raise StorageError("private database path")

        app.state.storage.get_collector_state = unreadable_state
        response = client.get("/api/collector/status")

    assert response.status_code == 200
    assert response.json()["state"] == "stopped_storage"
    assert response.json()["reason"] == "Speicher- oder Zustandsfehler; Erfassung angehalten"
    assert "private database path" not in response.text


def test_history_events_and_csv_are_database_only_and_keep_original_rows() -> None:
    with TestClient(app) as client:
        store = app.state.storage
        store.record_cycle(
            {
                "request_id": "synthetic-request",
                "started_at": "2026-10-14T12:00:00+00:00",
                "completed_at": "2026-10-14T12:00:01+00:00",
                "function_code": 3,
                "unit_id": 255,
                "offset": 4102,
                "register_count": 1,
                "outcome": "ok",
            },
            [{
                "observation_id": "synthetic-observation",
                "signal_id": "boiler.temperature",
                "observed_at": "2026-10-14T12:00:01+00:00",
                "value": 42,
                "unit": "°C",
                "quality": "ok",
                "raw_words": [42],
                "source": "synthetic",
                "profile_id": "core",
                "profile_version": "1",
                "decoder_version": "1",
            }],
        )
        current = client.get("/api/signals/current")
        history = client.get("/api/history/boiler.temperature?limit=1")
        csv_response = client.get("/api/export.csv")
        event_page = client.get("/api/events?limit=1")

    assert current.status_code == 200
    assert current.json()["signals"][0]["value"] == 42
    assert current.json()["signals"][0]["unit"] == "°C"
    assert current.json()["signals"][0]["quality"] == "ok"
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["raw_words"] == [42]
    assert "synthetic-observation" in csv_response.text
    assert "2026-10-14T12:00:01+00:00" in csv_response.text
    assert event_page.status_code == 200


def test_mutating_routes_require_same_origin_custom_header_and_log_config_change() -> None:
    with TestClient(app) as client:
        denied = client.put("/api/config", json={"display_timezone": "UTC"})
        changed = client.put(
            "/api/config",
            json={"display_timezone": "Europe/Vienna"},
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
                "X-Requested-With": "SommerauerMonitor",
            },
        )
        config = client.get("/api/config").json()
        events = client.get("/api/events").json()

    assert denied.status_code == 403
    assert changed.status_code == 200
    assert config["display_timezone"] == "Europe/Vienna"
    assert "configuration_changed" in {event["kind"] for event in events["items"]}


@pytest.mark.parametrize("origin", [
    "https://monitor.example.invalid",
    "http://testserver",
])
def test_proxy_origin_and_direct_access_can_save_configuration(monkeypatch, origin) -> None:
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://monitor.example.invalid")
    with TestClient(app) as client:
        response = client.put(
            "/api/config", json={"display_timezone": "UTC"},
            headers={**MUTATION_HEADERS, "Origin": origin},
        )
        assert response.status_code == 200
        assert client.get("/api/config").json()["display_timezone"] == "UTC"
        assert "monitor.example.invalid" not in client.get("/api/config").text


@pytest.mark.parametrize("headers", [
    {"Origin": "https://foreign.example.invalid"},
    {"Origin": "http://monitor.example.invalid"},
    {"Origin": "https://monitor.example.invalid:8443"},
    {"Origin": "https://monitor.example.invalid.foreign.invalid"},
    {"Origin": "null"},
    {"Origin": ""},
    {"Sec-Fetch-Site": "cross-site"},
    {"X-Requested-With": ""},
    {"Origin": "https://foreign.example.invalid",
     "X-Forwarded-Host": "foreign.example.invalid", "X-Forwarded-Proto": "https"},
])
def test_proxy_origin_rejects_untrusted_mutations_without_effect(monkeypatch, headers) -> None:
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://monitor.example.invalid")
    with TestClient(app) as client:
        before = client.get("/api/config").json()
        response = client.put(
            "/api/config", json={"display_timezone": "UTC"},
            headers={**MUTATION_HEADERS, "Origin": "https://monitor.example.invalid", **headers},
        )
        assert response.status_code == 403
        assert client.get("/api/config").json() == before
        assert client.get("/api/events").json()["items"] == []


def test_proxy_origin_requires_explicit_deployment_configuration() -> None:
    with TestClient(app) as client:
        response = client.put(
            "/api/config", json={"display_timezone": "UTC"},
            headers={**MUTATION_HEADERS, "Origin": "https://monitor.example.invalid"},
        )
        assert response.status_code == 403
        assert client.get("/api/config").json()["display_timezone"] == "Europe/Vienna"


@pytest.mark.parametrize("origin", [
    "*", "https://*.example.invalid", "file:///tmp/monitor", "monitor.example.invalid",
    "https://user:password@monitor.example.invalid", "https://monitor.example.invalid/app",
    "https://monitor.example.invalid?query=1", "https://monitor.example.invalid#fragment",
])
def test_public_origin_rejects_non_origin_configuration(origin) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, PUBLIC_ORIGIN=origin)


def test_history_rejects_naive_or_reversed_ranges() -> None:
    with TestClient(app) as client:
        naive = client.get("/api/history/boiler.temperature?start=2026-10-14T12:00:00")
        reversed_range = client.get(
            "/api/history/boiler.temperature?start=2026-10-15T00:00:00Z&end=2026-10-14T00:00:00Z"
        )

    assert naive.status_code == 422
    assert reversed_range.status_code == 422


def test_history_distinguishes_repeated_local_hour_at_dst_fallback() -> None:
    with TestClient(app) as client:
        for index, observed_at in enumerate(
            ("2026-10-25T00:45:00+00:00", "2026-10-25T01:15:00+00:00")
        ):
            app.state.storage.record_cycle(
                {
                    "request_id": f"dst-request-{index}",
                    "started_at": observed_at,
                    "completed_at": observed_at,
                    "function_code": 3,
                    "unit_id": 255,
                    "offset": 4102,
                    "register_count": 1,
                    "outcome": "ok",
                },
                [{
                    "observation_id": f"dst-observation-{index}",
                    "signal_id": "boiler.temperature",
                    "observed_at": observed_at,
                    "value": 40 + index,
                    "unit": "°C",
                    "quality": "ok",
                    "raw_words": [40 + index],
                    "source": "synthetic",
                    "profile_id": "core",
                    "profile_version": "1",
                    "decoder_version": "1",
                }],
            )
        response = client.get(
            "/api/history/boiler.temperature"
            "?start=2026-10-25T02:30:00%2B02:00&end=2026-10-25T02:30:00%2B01:00"
        )

    assert response.status_code == 200
    assert [item["value"] for item in response.json()["items"]] == [40, 41]
