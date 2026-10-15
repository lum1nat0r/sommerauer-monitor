"""Synthetische Runner-Abnahme; ausschließlich isolierter Speicher und Loopback."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import subprocess
import sys
import threading
import time

import pytest

from backend.catalog import build_read_blocks, load_catalog
from backend.collector import Collector
from backend.config import Settings
from backend.device_lock import DeviceLock, DeviceOwnershipError
from backend.modbus import (
    ConnectionError as ModbusConnectionError,
    IncompleteResponseError,
    ProtocolError,
    RegisterRead,
)
from backend.modbus_simulator import ModbusSimulator
from backend.read_checks import ReadCheckError, ReadCheckRunner
from backend.storage import SQLiteStore, StorageError


class FakeClock:
    def __init__(self):
        self.elapsed = 0.0
        self.origin = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def monotonic(self):
        return self.elapsed

    def now(self):
        return self.origin + timedelta(seconds=self.elapsed)


class FakeClient:
    VALUES = {4098: (0,), 4099: (173,), 4102: (42,), 28688: (4, 319), 33408: (65526,)}

    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.delay = 0.0
        self.failure = None
        self.values = dict(self.VALUES)

    def read_catalog(self, block):
        self.calls.append((block.offset, block.count, self.clock.monotonic()))
        self.clock.elapsed += self.delay
        if self.failure is not None:
            raise self.failure
        return RegisterRead(block.offset, self.values[block.offset])


def make_plan(settings, offsets=(4098, 4099, 33408)):
    identifiers = [f"register:{offset}" for offset in offsets]
    blocks = build_read_blocks(identifiers)
    binding = {
        "host": settings.modbus_host.casefold(),
        "port": settings.modbus_port,
        "unit_id": 255,
        "source": settings.diagnostics_source,
        "catalog_sha256": load_catalog().sha256,
    }
    return {
        "schema_version": 1,
        "catalog_sha256": binding["catalog_sha256"],
        "register_ids": identifiers,
        "blocks": [{"offset": block.offset, "count": block.count} for block in blocks],
        "purpose": "Endliche synthetische Offline-Abnahme",
        "source": settings.diagnostics_source,
        "target": {"host": settings.modbus_host, "port": settings.modbus_port},
        "target_fingerprint": hashlib.sha256(
            json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "function_code": 3,
        "unit_id": 255,
        "deadline_seconds": 3,
        "request_budget": len(blocks),
        "min_interval_seconds": 60,
        "max_duration_seconds": 600,
        "stop_conditions": [
            "transport", "protocol", "data", "storage", "operator", "anomaly", "expired",
        ],
    }


@pytest.fixture
def setup_runner(tmp_path):
    settings = Settings(
        _env_file=None, MODBUS_HOST="127.0.0.1", DIAGNOSTICS_SOURCE="simulator",
        DATA_DIR=tmp_path,
    )
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    clock = FakeClock()
    client = FakeClient(clock)
    runner = ReadCheckRunner(
        settings=settings, store=store, collector=None, client=client,
        monotonic=clock.monotonic, now=clock.now,
    )
    try:
        yield runner, store, client, clock, settings
    finally:
        runner.close()


def plan_run(store, settings, offsets=(4098, 4099, 33408)):
    return store.create_diagnostic_run(make_plan(settings, offsets))["run_id"]


def assert_error(code, action):
    with pytest.raises(ReadCheckError) as caught:
        action()
    assert caught.value.code == code
    return caught.value


def assert_sanitized(document, settings, fingerprint):
    encoded = json.dumps(document)
    assert settings.modbus_host not in encoded
    assert str(settings.data_dir) not in encoded
    assert fingerprint not in encoded
    assert '"target"' not in encoded
    assert '"target_fingerprint"' not in encoded


def test_three_manual_reads_preserve_raw_words_and_never_create_observations(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    fingerprint = store.get_diagnostic_run(run_id)["plan"]["target_fingerprint"]
    opened = runner.start(run_id)
    assert (opened["state"], opened["run_id"], opened["requests_reserved"]) == (
        "running", run_id, 0,
    )
    assert client.calls == []
    assert_sanitized(opened, settings, fingerprint)
    for step, words in enumerate(([0], [173], [65526])):
        clock.elapsed += 60
        answer = runner.read_next(run_id, step)
        assert answer["state"] == "awaiting_review"
        request = answer["requests"][step]
        assert request["raw_words"] == words
        assert request["decoded_signals"] == []
        assert request["interpretation_status"] == "raw_only"
        assert_sanitized(answer, settings, fingerprint)
        assert len(client.calls) == step + 1
        reviewed = runner.review(run_id, step, "continue", "Synthetisch geprüft")
        assert reviewed["state"] == ("completed" if step == 2 else "running")
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 3
    assert [row["raw_words"] for row in saved["requests"]] == [[0], [173], [65526]]
    assert [row["review"]["observation"] for row in saved["requests"]] == [
        "Synthetisch geprüft",
    ] * 3
    assert [(offset, count) for offset, count, _ in client.calls] == [
        (4098, 1), (4099, 1), (33408, 1),
    ]
    assert store.count_observations() == 0
    assert store.get_collector_state() is None
    assert_error("run_conflict", lambda: runner.start(run_id))


def test_counter_second_word_selection_reads_and_decodes_complete_pair(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings, (28689,))
    runner.start(run_id)
    clock.elapsed = 60
    answer = runner.read_next(run_id, 0)
    request = answer["requests"][0]
    assert client.calls == [(28688, 2, 60)]
    assert request["raw_words"] == [4, 319]
    assert request["interpretation_status"] == "confirmed_core"
    assert [(signal["signal_id"], signal["value"]) for signal in request["decoded_signals"]] == [
        ("boiler.operating_minutes", 6079),
    ]
    assert store.count_observations() == 0


def test_first_read_is_due_at_exactly_sixty_seconds_without_waiting(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 59.999
    assert_error("read_not_due", lambda: runner.read_next(run_id, 0))
    assert clock.elapsed == 59.999
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 0
    assert client.calls == []
    clock.elapsed = 60
    assert runner.read_next(run_id, 0)["state"] == "awaiting_review"
    assert len(client.calls) == 1


def test_interval_starts_after_response_and_storage_complete(setup_runner, monkeypatch):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    finish = store.finish_diagnostic_request

    def slow_finish(*args, **kwargs):
        clock.elapsed += 17
        return finish(*args, **kwargs)

    monkeypatch.setattr(store, "finish_diagnostic_request", slow_finish)
    client.delay = 11
    runner.start(run_id)
    clock.elapsed = 60
    runner.read_next(run_id, 0)
    assert clock.elapsed == 88
    runner.review(run_id, 0, "continue", None)
    clock.elapsed = 147.999
    assert_error("read_not_due", lambda: runner.read_next(run_id, 1))
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1
    assert len(client.calls) == 1
    clock.elapsed = 148
    runner.read_next(run_id, 1)
    assert len(client.calls) == 2
    assert client.calls[1][2] == 148


def test_slow_reservation_over_deadline_consumes_budget_without_socket(setup_runner, monkeypatch):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    reserve = store.reserve_diagnostic_request

    def slow_reserve(*args, **kwargs):
        reserve(*args, **kwargs)
        clock.elapsed = 600

    monkeypatch.setattr(store, "reserve_diagnostic_request", slow_reserve)
    runner.start(run_id)
    clock.elapsed = 60
    answer = runner.read_next(run_id, 0)
    assert answer["state"] == "expired"
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["outcome"] != "reserved"
    assert client.calls == []


def test_duplicate_start_steps_and_reviews_cannot_replay_or_overwrite(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    assert_error("run_conflict", lambda: runner.start(run_id))
    clock.elapsed = 60
    assert_error("run_conflict", lambda: runner.read_next(run_id, 1))
    runner.read_next(run_id, 0)
    for step in (0, 1):
        assert_error("run_conflict", lambda: runner.read_next(run_id, step))
    before = store.get_diagnostic_run(run_id)["requests"][0]
    runner.review(run_id, 0, "continue", "Erste Bewertung")
    assert_error("run_conflict", lambda: runner.review(run_id, 0, "anomaly", "Veraltet"))
    after = store.get_diagnostic_run(run_id)["requests"][0]
    assert after["raw_words"] == before["raw_words"]
    assert after["decoded"] == before["decoded"]
    assert after["review"]["observation"] == "Erste Bewertung"
    assert len(client.calls) == 1
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1


@pytest.mark.parametrize(("verdict", "state"), [("finish", "cancelled"), ("anomaly", "stopped_data")])
def test_review_ends_run_without_changing_device_answer(setup_runner, verdict, state):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 60
    runner.read_next(run_id, 0)
    answer = runner.review(run_id, 0, verdict, "Betreiberbeobachtung")
    assert answer["state"] == state
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests"][0]["raw_words"] == [0]
    assert saved["requests"][0]["review"]["verdict"] == verdict
    assert len(client.calls) == 1
    assert_error("run_conflict", lambda: runner.read_next(run_id, 1))


@pytest.mark.parametrize("step", [0, 1])
@pytest.mark.parametrize(
    ("error_type", "received_bytes", "state"),
    [(ModbusConnectionError, 0, "stopped_transport"),
     (IncompleteResponseError, 4, "stopped_protocol"),
     (ProtocolError, 9, "stopped_protocol")],
)
def test_transport_failure_stops_without_retry_and_redacts_exception(
    setup_runner, step, error_type, received_bytes, state,
):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 60
    if step:
        runner.read_next(run_id, 0)
        runner.review(run_id, 0, "continue", None)
        clock.elapsed += 60
    client.failure = error_type("privates-ziel.invalid C:/geheim", received_bytes=received_bytes)
    answer = runner.read_next(run_id, step)
    assert answer["state"] == state
    assert "privates-ziel" not in json.dumps(answer)
    assert "geheim" not in json.dumps(answer)
    saved = store.get_diagnostic_run(run_id)
    request = saved["requests"][step]
    assert request["error_class"]
    assert request["received_bytes"] == received_bytes
    assert saved["requests_reserved"] == step + 1
    assert_error("run_conflict", lambda: runner.read_next(run_id, step))
    assert len(client.calls) == step + 1


def test_core_data_error_preserves_raw_words_and_blocks_remaining_plan(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings, (4102, 33408))
    client.values[4102] = (110,)
    runner.start(run_id)
    clock.elapsed = 60
    answer = runner.read_next(run_id, 0)
    assert answer["state"] == "stopped_data"
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests"][0]["raw_words"] == [110]
    assert saved["requests"][0]["decoded"] is None
    assert store.diagnostic_access_blocker() == run_id
    assert store.count_observations() == 0
    assert_error("run_conflict", lambda: runner.read_next(run_id, 1))
    assert len(client.calls) == 1


def test_storage_failure_retains_reservation_and_recovery_never_replays(setup_runner, monkeypatch):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 60

    def broken(*args, **kwargs):
        raise StorageError("privater/pfad nicht beschreibbar")

    with monkeypatch.context() as patch:
        patch.setattr(store, "finish_diagnostic_request", broken)
        patch.setattr(store, "set_diagnostic_run_state", broken)
        error = assert_error("stopped_storage", lambda: runner.read_next(run_id, 0))
        assert "privater/pfad" not in str(error)
        assert_error("stopped_storage", lambda: runner.read_next(run_id, 1))
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["outcome"] == "reserved"
    runner.close()
    restored = ReadCheckRunner(
        settings=settings, store=store, collector=None, client=client,
        monotonic=clock.monotonic, now=clock.now,
    )
    try:
        restored.recover_interrupted()
        assert store.get_diagnostic_run(run_id)["state"] == "interrupted"
        assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1
        assert_error("run_conflict", lambda: restored.start(run_id))
        assert len(client.calls) == 1
    finally:
        restored.close()


@pytest.mark.parametrize("active_state", ["running", "awaiting_review"])
def test_crash_recovery_requires_ownership_and_preserves_consumed_attempts(setup_runner, active_state):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    store.set_diagnostic_run_state(run_id, "running", None)
    store.reserve_diagnostic_request(run_id, 0, clock.now().isoformat())
    if active_state == "awaiting_review":
        store.finish_diagnostic_request(run_id, 0, {
            "outcome": "ok", "raw_words": [0], "decoded": None,
            "error_class": None, "received_bytes": 11,
        }, "awaiting_review")
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    try:
        with pytest.raises(DeviceOwnershipError):
            runner.recover_interrupted()
        assert store.get_diagnostic_run(run_id)["state"] == active_state
        assert client.calls == []
    finally:
        owner.release()
    runner.recover_interrupted()
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == "interrupted"
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["raw_words"] == ([0] if active_state == "awaiting_review" else None)
    assert_error("run_conflict", lambda: runner.start(run_id))
    store.acknowledge_diagnostic_run(run_id, "Synthetischen Abbruch geklärt")
    assert_error("run_conflict", lambda: runner.start(run_id))
    new_id = plan_run(store, settings, (4098,))
    assert runner.start(new_id)["state"] == "running"
    assert client.calls == []


@pytest.mark.parametrize("change", ["host", "port", "source", "catalog"])
def test_changed_binding_rejects_old_plan_before_any_read(setup_runner, change):
    runner, store, client, _, settings = setup_runner
    plan = make_plan(settings)
    if change == "host":
        settings.modbus_host = "localhost"
        settings.diagnostics_source = "device"
    elif change == "port":
        settings.modbus_port += 1
    elif change == "source":
        settings.diagnostics_source = "device"
    else:
        plan["catalog_sha256"] = "0" * 64
    run_id = store.create_diagnostic_run(plan)["run_id"]
    assert_error("plan_changed", lambda: runner.start(run_id))
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 0
    assert client.calls == []


@pytest.mark.parametrize(("attribute", "value", "code"), [
    ("modbus_host", None, "unconfigured"), ("modbus_unit_id", 1, "invalid_unit"),
])
def test_missing_host_or_wrong_unit_blocks_before_socket(setup_runner, attribute, value, code):
    runner, store, client, _, settings = setup_runner
    run_id = plan_run(store, settings)
    setattr(settings, attribute, value)
    assert_error(code, lambda: runner.start(run_id))
    assert client.calls == []


@pytest.mark.parametrize("state", [
    {"state": "running"}, {"state": "reconnect_wait"}, {"state": "stopped_data"},
    {"state": "paused", "reconnect_attempts": 1},
    {"state": "completed", "request_in_flight": True},
    {"state": "paused", "error": "synthetischer Fehler"},
])
def test_persisted_unclean_core_state_blocks_start_without_collector(setup_runner, state):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    store.save_collector_state(state, clock.now().isoformat())
    assert_error("core_blocked", lambda: runner.start(run_id))
    assert store.get_collector_state() == state
    assert client.calls == []


@pytest.mark.parametrize("state", ["paused", "completed"])
def test_clean_persisted_core_stop_permits_diagnosis_without_restart(setup_runner, state):
    runner, store, client, clock, settings = setup_runner
    store.save_collector_state({"state": state}, clock.now().isoformat())
    run_id = plan_run(store, settings)
    assert runner.start(run_id)["state"] == "running"
    runner.stop(run_id)
    assert store.get_collector_state() == {"state": state}
    assert client.calls == []


def test_public_mode_lock_is_reentrant_and_close_is_idempotent(setup_runner):
    runner, store, client, _, settings = setup_runner
    assert isinstance(runner.stop_event, threading.Event)
    run_id = plan_run(store, settings)
    with runner.mode_lock:
        with runner.mode_lock:
            assert runner.start(run_id)["state"] == "running"
    runner.close()
    runner.close()
    assert store.get_diagnostic_run(run_id)["state"] == "cancelled"
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    owner.release()
    assert client.calls == []


def test_two_browser_calls_reserve_only_once(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 60
    barrier = threading.Barrier(2)

    def click():
        barrier.wait(timeout=2)
        try:
            return runner.read_next(run_id, 0)["state"]
        except ReadCheckError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: click(), range(2)))
    assert sorted(results) == ["awaiting_review", "run_conflict"]
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1
    assert len(client.calls) == 1


@pytest.mark.parametrize("hard_error", [False, True])
@pytest.mark.parametrize("shutdown", ["stop", "close"])
def test_stop_sets_event_before_lock_and_preserves_inflight_result(setup_runner, hard_error, shutdown):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    entered = threading.Event()
    release = threading.Event()
    original = client.read_catalog

    def gated(block):
        entered.set()
        assert release.wait(3)
        if hard_error:
            client.failure = ProtocolError("Synthetische Ausnahme", received_bytes=9)
        return original(block)

    client.read_catalog = gated
    runner.start(run_id)
    clock.elapsed = 60
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(runner.read_next, run_id, 0)
        assert entered.wait(2)
        stopping = (pool.submit(runner.stop, run_id) if shutdown == "stop"
                    else pool.submit(runner.close))
        try:
            assert runner.stop_event.wait(2)
            owner = DeviceLock(settings.data_dir / "collector.lock")
            with pytest.raises(DeviceOwnershipError):
                owner.acquire()
        finally:
            release.set()
        reading.result(timeout=3)
        stopping.result(timeout=3)
    if shutdown == "close":
        assert all(not worker.is_alive() for worker in runner._workers)
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == ("stopped_protocol" if hard_error else "cancelled")
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["raw_words"] == (None if hard_error else [0])
    owner.acquire()
    owner.release()
    assert len(client.calls) == 1


def test_watchdog_expires_without_any_browser_action_or_read(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 600
    deadline = time.perf_counter() + 3
    while store.get_diagnostic_run(run_id)["state"] == "running" and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert store.get_diagnostic_run(run_id)["state"] == "expired"
    assert client.calls == []
    runner.close()
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    owner.release()


@pytest.mark.parametrize(("second_words", "state"), [
    ((4, 320), "awaiting_review"), ((4, 318), "stopped_data"), ((4, 400), "stopped_data"),
])
def test_counter_progression_checks_previous_run_with_same_fingerprint(setup_runner, second_words, state):
    runner, store, client, clock, settings = setup_runner
    first = plan_run(store, settings, (28689,))
    runner.start(first)
    clock.elapsed = 60
    runner.read_next(first, 0)
    runner.review(first, 0, "continue", None)
    second = plan_run(store, settings, (28689,))
    runner.start(second)
    clock.elapsed += 60
    client.values[28688] = second_words
    assert runner.read_next(second, 0)["state"] == state
    assert store.get_diagnostic_run(second)["requests"][0]["raw_words"] == list(second_words)
    assert store.count_observations() == 0


def test_counter_evidence_of_another_target_is_not_compared(setup_runner):
    runner, store, client, clock, settings = setup_runner
    first = plan_run(store, settings, (28689,))
    runner.start(first)
    clock.elapsed = 60
    runner.read_next(first, 0)
    runner.review(first, 0, "continue", None)
    settings.modbus_port += 1
    second = plan_run(store, settings, (28689,))
    runner.start(second)
    clock.elapsed += 60
    client.values[28688] = (0, 1)
    assert runner.read_next(second, 0)["state"] == "awaiting_review"


def test_actual_loopback_service_persists_three_explicit_fc03_answers(tmp_path):
    with ModbusSimulator(catalog=True) as simulator:
        host, port = simulator.address
        settings = Settings(
            _env_file=None, MODBUS_HOST=host, MODBUS_PORT=port,
            DIAGNOSTICS_SOURCE="simulator", DATA_DIR=tmp_path,
        )
        store = SQLiteStore(tmp_path / "loopback.sqlite3")
        clock = FakeClock()
        runner = ReadCheckRunner(
            settings=settings, store=store, collector=None,
            monotonic=clock.monotonic, now=clock.now,
        )
        try:
            run_id = plan_run(store, settings)
            runner.start(run_id)
            assert simulator.received_requests == ()
            for step in range(3):
                clock.elapsed += 60
                assert runner.read_next(run_id, step)["state"] == "awaiting_review"
                runner.review(run_id, step, "continue", "Synthetischer Loopbackbeleg")
            assert simulator.received_requests == (
                (255, 3, 4098, 1), (255, 3, 4099, 1), (255, 3, 33408, 1),
            )
            saved = SQLiteStore(tmp_path / "loopback.sqlite3").get_diagnostic_run(run_id)
            assert saved["state"] == "completed"
            assert saved["requests_reserved"] == 3
            assert [row["raw_words"] for row in saved["requests"]] == [[0], [173], [65526]]
            assert store.count_observations() == 0
        finally:
            runner.close()


@pytest.mark.parametrize("host", ["localhost", "::1", "192.0.2.1", None])
def test_simulator_source_requires_exact_ipv4_loopback(tmp_path, host):
    with pytest.raises(ValueError, match="127.0.0.1"):
        Settings(
            _env_file=None, MODBUS_HOST=host, DIAGNOSTICS_SOURCE="simulator",
            DATA_DIR=tmp_path,
        )


def test_device_source_is_default_and_loopback_is_not_implicitly_synthetic(tmp_path, monkeypatch):
    monkeypatch.delenv("DIAGNOSTICS_SOURCE", raising=False)
    settings = Settings(_env_file=None, MODBUS_HOST="127.0.0.1", DATA_DIR=tmp_path)
    assert settings.diagnostics_source == "device"


@pytest.mark.parametrize("stage", ["reserve", "start", "error_result"])
def test_storage_errors_block_every_following_action(setup_runner, monkeypatch, stage):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)

    def broken(*args, **kwargs):
        raise StorageError("C:/privater/pfad synthetisch nicht verfügbar")

    if stage == "start":
        monkeypatch.setattr(store, "set_diagnostic_run_state", broken)
        def action():
            return runner.start(run_id)
    else:
        runner.start(run_id)
        clock.elapsed = 60
        if stage == "reserve":
            monkeypatch.setattr(store, "reserve_diagnostic_request", broken)
        else:
            client.failure = ProtocolError("Synthetischer Protokollfehler", received_bytes=9)
            monkeypatch.setattr(store, "finish_diagnostic_request", broken)
        def action():
            return runner.read_next(run_id, 0)
    error = assert_error("stopped_storage", action)
    assert "privater" not in str(error)
    assert_error("stopped_storage", lambda: runner.read_next(run_id, 0))
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == (1 if stage == "error_result" else 0)
    assert len(client.calls) == (1 if stage == "error_result" else 0)


@pytest.mark.parametrize("last_request_error", [False, True])
def test_start_waits_for_collector_join_and_rechecks_last_request(
    setup_runner, last_request_error,
):
    runner, store, client, clock, settings = setup_runner
    runner.close()
    joined = threading.Event()

    class CollectorDouble:
        state = "running"
        error = None

        def status(self):
            return {"reconnect_attempts": 0}

        def stop(self):
            assert client.calls == []
            if last_request_error:
                self.state = "stopped_protocol"
                self.error = "Synthetischer Fehler der letzten Anfrage"
            else:
                self.state = "paused"
            store.save_collector_state(
                {"state": self.state, "error": self.error}, clock.now().isoformat(),
            )
            joined.set()

    replacement = ReadCheckRunner(
        settings=settings, store=store, collector=CollectorDouble(), client=client,
        monotonic=clock.monotonic, now=clock.now,
    )
    try:
        run_id = plan_run(store, settings)
        if last_request_error:
            assert_error("core_blocked", lambda: replacement.start(run_id))
            assert store.get_diagnostic_run(run_id)["state"] == "planned"
        else:
            assert replacement.start(run_id)["state"] == "running"
        assert joined.is_set()
        assert client.calls == []
    finally:
        replacement.close()


def test_collector_join_timeout_does_not_open_diagnostics(setup_runner):
    runner, store, client, clock, settings = setup_runner
    runner.close()

    class StuckCollector:
        state = "running"
        error = None

        def status(self):
            return {"reconnect_attempts": 0}

        def stop(self):
            raise TimeoutError("Synthetischer Join-Timeout")

    replacement = ReadCheckRunner(
        settings=settings, store=store, collector=StuckCollector(), client=client,
        monotonic=clock.monotonic, now=clock.now,
    )
    try:
        run_id = plan_run(store, settings)
        assert_error("run_conflict", lambda: replacement.start(run_id))
        assert store.get_diagnostic_run(run_id)["state"] == "planned"
        assert client.calls == []
        owner = DeviceLock(settings.data_dir / "collector.lock")
        owner.acquire()
        owner.release()
    finally:
        replacement.close()


@pytest.mark.parametrize("change", ["stop", "target"])
def test_reservation_race_consumes_attempt_without_read(setup_runner, monkeypatch, change):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    reserve = store.reserve_diagnostic_request

    def reserve_then_change(*args, **kwargs):
        reserve(*args, **kwargs)
        if change == "stop":
            runner.stop_event.set()
        else:
            settings.modbus_port += 1

    monkeypatch.setattr(store, "reserve_diagnostic_request", reserve_then_change)
    runner.start(run_id)
    clock.elapsed = 60
    answer = runner.read_next(run_id, 0)
    assert answer["state"] == ("cancelled" if change == "stop" else "stopped_data")
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["outcome"] != "reserved"
    assert client.calls == []


@pytest.mark.parametrize("hard_error", [False, True])
def test_deadline_during_response_keeps_hard_error_and_releases_owner(setup_runner, hard_error):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 599
    client.delay = 2
    if hard_error:
        client.failure = ProtocolError("Synthetischer Fehler an der Frist", received_bytes=9)
    answer = runner.read_next(run_id, 0)
    assert answer["state"] == ("stopped_protocol" if hard_error else "expired")
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests"][0]["raw_words"] == (None if hard_error else [0])
    assert saved["requests_reserved"] == 1
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    owner.release()


@pytest.mark.parametrize("answer", [
    RegisterRead(4099, (0,)),
    RegisterRead(4098, (0,), unit_id=1),
    RegisterRead(4098, (0,), function_code=4),
    RegisterRead(4098, (0, 1)),
])
def test_invalid_injected_response_stops_protocol_without_followup(setup_runner, answer):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    original = client.read_catalog

    def malformed(block):
        original(block)
        return answer

    client.read_catalog = malformed
    runner.start(run_id)
    clock.elapsed = 60
    assert runner.read_next(run_id, 0)["state"] == "stopped_protocol"
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1
    assert_error("run_conflict", lambda: runner.read_next(run_id, 1))
    assert len(client.calls) == 1


@pytest.mark.parametrize("hard_error", [False, True])
def test_real_collector_hands_ownership_to_runner_only_after_final_response(setup_runner, hard_error):
    old_runner, store, client, clock, settings = setup_runner
    old_runner.close()
    entered, release = threading.Event(), threading.Event()

    class GatedCoreClient:
        def read(self, block):
            entered.set()
            assert release.wait(3)
            if hard_error:
                raise ProtocolError("Letzte synthetische Kernantwort fehlerhaft", received_bytes=9)
            return RegisterRead(block.offset, (42,))

    collector = Collector(
        host="127.0.0.1", port=502, store=store, data_dir=settings.data_dir,
        client=GatedCoreClient(), max_requests=1,
    )
    runner = ReadCheckRunner(
        settings=settings, store=store, collector=collector, client=client,
        monotonic=clock.monotonic, now=clock.now,
    )
    run_id = plan_run(store, settings)
    try:
        collector.start()
        assert entered.wait(2)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(runner.start, run_id)
            try:
                assert collector._stop.wait(2)
                assert not future.done()
                owner = DeviceLock(settings.data_dir / "collector.lock")
                with pytest.raises(DeviceOwnershipError):
                    owner.acquire()
                assert client.calls == []
            finally:
                release.set()
            if hard_error:
                with pytest.raises(ReadCheckError) as caught:
                    future.result(timeout=3)
                assert caught.value.code == "core_blocked"
                assert store.get_diagnostic_run(run_id)["state"] == "planned"
                owner.acquire()
                owner.release()
            else:
                assert future.result(timeout=3)["state"] == "running"
                assert not collector._request_in_flight
                clock.elapsed = 60
                assert runner.read_next(run_id, 0)["state"] == "awaiting_review"
                assert len(client.calls) == 1
    finally:
        release.set()
        runner.close()
        collector.stop()


def test_process_exit_after_runner_reservation_preserves_budget_for_locked_recovery(setup_runner):
    runner, store, client, _, settings = setup_runner
    run_id = plan_run(store, settings)
    code = """
import os
import sys
from backend.config import Settings
from backend.read_checks import ReadCheckRunner
from backend.storage import SQLiteStore
class ExitClient:
    def read_catalog(self, block):
        os._exit(17)
clock = [0.0]
settings = Settings(_env_file=None, MODBUS_HOST='127.0.0.1',
                    DIAGNOSTICS_SOURCE='simulator', DATA_DIR=sys.argv[1])
runner = ReadCheckRunner(settings=settings, store=SQLiteStore(sys.argv[2]),
                         collector=None, client=ExitClient(), monotonic=lambda: clock[0])
runner.start(sys.argv[3])
clock[0] = 60.0
runner.read_next(sys.argv[3], 0)
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(settings.data_dir), str(store.path), run_id],
        capture_output=True, text=True, timeout=10,
    )
    assert process.returncode == 17, process.stderr
    before = store.get_diagnostic_run(run_id)
    assert before["state"] == "running"
    assert before["requests_reserved"] == 1
    assert before["requests"][0]["outcome"] == "reserved"
    runner.recover_interrupted()
    after = store.get_diagnostic_run(run_id)
    assert after["state"] == "interrupted"
    assert after["requests_reserved"] == 1
    assert_error("run_conflict", lambda: runner.start(run_id))
    assert client.calls == []


def test_detected_binding_change_ends_active_run_even_if_target_is_restored(setup_runner):
    runner, store, client, clock, settings = setup_runner
    run_id = plan_run(store, settings)
    runner.start(run_id)
    clock.elapsed = 60
    settings.modbus_port += 1
    assert_error("plan_changed", lambda: runner.read_next(run_id, 0))
    settings.modbus_port -= 1
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == "stopped_data"
    assert saved["requests_reserved"] == 0
    assert store.diagnostic_access_blocker() == run_id
    assert_error("run_conflict", lambda: runner.read_next(run_id, 0))
    assert client.calls == []
