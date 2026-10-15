from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.collector import Collector
from backend.config import Settings, get_settings
from backend.device_lock import DeviceLock, DeviceOwnershipError
from backend.main import app
from backend.modbus import RegisterRead
from backend.read_checks import ReadCheckError, ReadCheckRunner
from backend.storage import SQLiteStore, StorageError, utc_now

MUTATION_HEADERS = {
    "Origin": "http://testserver",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "SommerauerMonitor",
}


def _hold_device_lock(path: str, ready, release) -> None:
    owner = DeviceLock(Path(path))
    owner.acquire()
    try:
        ready.set()
        release.wait(15)
    finally:
        owner.release()


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.setenv("MODBUS_HOST", "")
    monkeypatch.setenv("MODBUS_PORT", "1502")
    monkeypatch.setenv("MODBUS_UNIT_ID", "255")
    monkeypatch.setenv("COLLECTOR_MAX_REQUESTS", "")
    monkeypatch.setenv("DIAGNOSTICS_SOURCE", "device")
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


@pytest.mark.parametrize("action", ["pause", "resume", "acknowledge-and-start"])
def test_collector_actions_wait_for_runner_mode_lock(
    monkeypatch: pytest.MonkeyPatch, action: str,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    monkeypatch.setattr(Collector, "start", lambda collector: None)
    invoked = threading.Event()
    entered = threading.Event()
    with TestClient(app) as client:
        collector = app.state.collector
        method = action.replace("-", "_")
        monkeypatch.setattr(collector, method, invoked.set)

        def request_action():
            entered.set()
            return client.post(f"/api/collector/{action}", headers=MUTATION_HEADERS)

        with ThreadPoolExecutor(max_workers=1) as pool:
            with app.state.runner.mode_lock:
                response = pool.submit(request_action)
                assert entered.wait(2)
                assert not invoked.wait(0.05)
            assert response.result(timeout=3).status_code == 200
        assert invoked.is_set()


@pytest.mark.parametrize(("failure", "code", "status"), [
    (StorageError("private synthetic storage path"), "storage_unavailable", 503),
    (ReadCheckError("run_conflict"), "run_conflict", 409),
])
def test_recovery_failure_keeps_read_api_and_blocks_every_collector_action(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, code: str, status: int,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    starts = []
    stops = []

    def fail_recovery(runner):
        raise failure

    monkeypatch.setattr(ReadCheckRunner, "recover_interrupted", fail_recovery)
    monkeypatch.setattr(Collector, "start", lambda collector: starts.append(True))
    monkeypatch.setattr(Collector, "stop", lambda collector: stops.append(True))
    with TestClient(app) as client:
        assert app.state.diagnostics_blocker == code
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/history/boiler.temperature").status_code == 200
        catalog = client.get("/api/diagnostics/catalog")
        assert catalog.status_code == 200
        assert catalog.json()["blockade"] == code
        for action in ("pause", "resume", "acknowledge-and-start"):
            denied = client.post(f"/api/collector/{action}", headers=MUTATION_HEADERS)
            assert denied.status_code == status
            assert denied.json()["detail"]["code"] == code
            assert "private synthetic" not in denied.text

    assert starts == stops == []


def _persist_abandoned_run(client: TestClient) -> tuple[str, dict]:
    created = client.post(
        "/api/diagnostics/runs",
        json={"register_ids": ["register:4098"], "purpose": "Synthetische Recoveryprüfung"},
        headers=MUTATION_HEADERS,
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    store = app.state.storage
    store.set_diagnostic_run_state(run_id, "running", None)
    store.reserve_diagnostic_request(run_id, 0, utc_now())
    return run_id, store.get_diagnostic_run(run_id)


def test_foreign_os_owner_preserves_active_run_and_keeps_read_api_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    with TestClient(app) as client:
        run_id, original = _persist_abandoned_run(client)

    starts = []
    requests = []

    class NoDeviceClient:
        def __init__(self, host, port):
            pass

        def read(self, block):
            requests.append(block)
            raise AssertionError("No device request is allowed during recovery conflict")

    monkeypatch.setattr("backend.collector.ModbusTcpClient", NoDeviceClient)
    monkeypatch.setattr(Collector, "start", lambda collector: starts.append(True))
    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    owner = context.Process(
        target=_hold_device_lock,
        args=(str(tmp_path / "collector.lock"), ready, release),
    )
    owner.start()
    try:
        assert ready.wait(5), "synthetic foreign owner did not acquire the OS lock"
        with TestClient(app) as client:
            assert app.state.diagnostics_blocker == "run_conflict"
            assert app.state.storage.get_diagnostic_run(run_id) == original
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/history/boiler.temperature").json()["total"] == 0
            assert client.get("/api/diagnostics/catalog").json()["blockade"] == "run_conflict"
            assert client.get(f"/api/diagnostics/runs/{run_id}").json()["state"] == "running"
            assert client.get(f"/api/diagnostics/runs/{run_id}/export").status_code == 200
            for action in ("pause", "resume", "acknowledge-and-start"):
                denied = client.post(f"/api/collector/{action}", headers=MUTATION_HEADERS)
                assert denied.status_code == 409
                assert denied.json()["detail"]["code"] == "run_conflict"
            denied = client.post(
                f"/api/diagnostics/runs/{run_id}/start",
                json={"other_readers_stopped": True}, headers=MUTATION_HEADERS,
            )
            assert denied.status_code == 409
            assert denied.json()["detail"]["code"] == "run_conflict"
        store = SQLiteStore(tmp_path / "monitor.sqlite3")
        assert store.get_diagnostic_run(run_id) == original
        assert store.get_collector_state() is None
        assert starts == requests == []
    finally:
        release.set()
        owner.join(5)
        if owner.is_alive():
            owner.terminate()
            owner.join(5)
    assert owner.exitcode == 0


def test_recovered_reservation_requires_acknowledgement_without_collector_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    with TestClient(app) as client:
        run_id, _ = _persist_abandoned_run(client)

    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    requests = []

    class NoDeviceClient:
        def __init__(self, host, port):
            pass

        def read(self, block):
            requests.append(block)
            raise AssertionError("Recovery and acknowledgement must not read the device")

    monkeypatch.setattr("backend.collector.ModbusTcpClient", NoDeviceClient)
    with TestClient(app) as client:
        saved = app.state.storage.get_diagnostic_run(run_id)
        assert saved["state"] == "interrupted"
        assert saved["requests_reserved"] == 1
        assert saved["requests"][0]["raw_words"] is None
        assert app.state.diagnostics_blocker is None
        for action in ("resume", "acknowledge-and-start"):
            denied = client.post(f"/api/collector/{action}", headers=MUTATION_HEADERS)
            assert denied.status_code == 409
            assert denied.json()["detail"]["code"] == "diagnostic_stop_unacknowledged"
        acknowledged = client.post(
            f"/api/diagnostics/runs/{run_id}/acknowledge",
            json={"resolution": "Synthetischen Prozessabbruch geprüft"},
            headers=MUTATION_HEADERS,
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["state"] == "interrupted"
        assert client.get("/api/collector/status").json()["state"] == "paused"
        assert requests == []


def test_disabled_collector_still_has_runner_and_shutdown_releases_active_diagnosis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    monkeypatch.setenv("DIAGNOSTICS_SOURCE", "simulator")
    with TestClient(app) as client:
        assert app.state.collector is None
        runner = app.state.runner
        assert isinstance(runner, ReadCheckRunner)
        assert client.get("/api/config").json()["diagnostics_source"] == "simulator"
        created = client.post(
            "/api/diagnostics/runs",
            json={"register_ids": ["register:4098"], "purpose": "Synthetischer Shutdown"},
            headers=MUTATION_HEADERS,
        )
        assert created.status_code == 201
        run_id = created.json()["run_id"]
        started = client.post(
            f"/api/diagnostics/runs/{run_id}/start",
            json={"other_readers_stopped": True}, headers=MUTATION_HEADERS,
        )
        assert started.status_code == 200
        assert started.json()["state"] == "running"
        assert runner.client is None
        owner = DeviceLock(tmp_path / "collector.lock")
        with pytest.raises(DeviceOwnershipError):
            owner.acquire()

    assert runner.stop_event.is_set()
    assert all(not worker.is_alive() for worker in runner._workers)
    assert runner.store.get_diagnostic_run(run_id)["state"] == "cancelled"
    assert runner.store.get_diagnostic_run(run_id)["requests_reserved"] == 0
    owner.acquire()
    owner.release()


def test_collector_started_explicitly_after_recovery_is_stopped_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODBUS_HOST", "127.0.0.1")
    with TestClient(app) as client:
        run_id, _ = _persist_abandoned_run(client)

    monkeypatch.setenv("COLLECTOR_ENABLED", "true")
    calls = []
    with TestClient(app) as client:
        collector = app.state.collector
        assert app.state.collector_started is False
        monkeypatch.setattr(collector, "start", lambda: calls.append("start"))
        monkeypatch.setattr(collector, "stop", lambda: calls.append("stop"))
        acknowledged = client.post(
            f"/api/diagnostics/runs/{run_id}/acknowledge",
            json={"resolution": "Synthetische Ursache geklärt"},
            headers=MUTATION_HEADERS,
        )
        assert acknowledged.status_code == 200
        assert calls == []
        started = client.post("/api/collector/acknowledge-and-start", headers=MUTATION_HEADERS)
        assert started.status_code == 200
        assert calls == ["start"]

    assert calls == ["start", "stop"]
