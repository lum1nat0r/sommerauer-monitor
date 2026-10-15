from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from backend.collector import Collector, CollectorStopped
from backend.device_lock import DeviceLock, DeviceOwnershipError
from backend.modbus import (
    ConnectionError as ModbusConnectionError,
    IncompleteResponseError,
    ProtocolError,
    RegisterRead,
)
from backend.storage import SQLiteStore, StorageError


class FakeClock:
    def __init__(self):
        self.elapsed = 0.0
        self.origin = datetime(2026, 10, 14, tzinfo=timezone.utc)

    def monotonic(self):
        return self.elapsed

    def now(self):
        return self.origin + timedelta(seconds=self.elapsed)

    def wait(self, event: threading.Event, seconds: float) -> bool:
        if event.is_set():
            return True
        self.elapsed += seconds
        return event.is_set()


class FakeClient:
    VALUES = {4102: (42,), 28688: (0, 0), 36864: (30, 20)}

    def __init__(self, clock: FakeClock, delay=0.0):
        self.clock = clock
        self.delay = delay
        self.starts = []
        self.ends = []

    def read(self, block):
        self.starts.append((block.offset, self.clock.monotonic()))
        self.clock.elapsed += self.delay
        self.ends.append(self.clock.monotonic())
        return RegisterRead(block.offset, self.VALUES[block.offset])


def make_collector(
    tmp_path, *, limit=3, duration=None, delay=0.0, store=None, retry_on_transport_error=True
):
    clock = FakeClock()
    client = FakeClient(clock, delay)
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=store or SQLiteStore(tmp_path / "monitor.sqlite3"),
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
        max_requests=limit,
        max_duration_seconds=duration,
        retry_on_transport_error=retry_on_transport_error,
    )
    return collector, client, clock


def diagnostic_run(store, state, *, reserve_request=True):
    binding = {
        "host": "127.0.0.1", "port": 1502, "unit_id": 255,
        "source": "simulator", "catalog_sha256": "a" * 64,
    }
    plan = {
        "schema_version": 1,
        "catalog_sha256": binding["catalog_sha256"],
        "register_ids": ["register:4098"],
        "blocks": [{"offset": 4098, "count": 1}],
        "purpose": "Synthetische Collector-Sperrprüfung",
        "source": "simulator",
        "target": {"host": binding["host"], "port": binding["port"]},
        "target_fingerprint": hashlib.sha256(
            json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "function_code": 3,
        "unit_id": 255,
        "deadline_seconds": 3,
        "request_budget": 1,
        "min_interval_seconds": 60,
        "max_duration_seconds": 600,
        "stop_conditions": ["transport", "protocol", "data", "storage", "operator", "expired"],
    }
    run_id = store.create_diagnostic_run(plan)["run_id"]
    if reserve_request:
        store.reserve_diagnostic_request(run_id, 0, "2026-10-15T12:00:00+00:00")
    elif state != "planned":
        store.set_diagnostic_run_state(run_id, "running", None)
    if state == "awaiting_review":
        store.finish_diagnostic_request(
            run_id, 0,
            {
                "outcome": "ok", "raw_words": [0], "decoded": None,
                "error_class": None, "received_bytes": 11,
                "completed_at": "2026-10-15T12:00:01+00:00",
            },
            "awaiting_review",
        )
    elif state not in {"planned", "running"}:
        store.set_diagnostic_run_state(run_id, state, "Synthetischer Diagnoseabschluss")
    return run_id


def test_budgeted_run_records_core_observations_and_stops(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=3)
    collector.run()

    assert collector.state == "completed"
    assert [offset for offset, _ in client.starts] == [4102, 28688, 36864]
    history = collector.store.history("boiler.temperature")
    assert [(row["value"], row["raw_words"]) for row in history] == [(42, [42])]
    assert collector.store.get_collector_state()["request_count"] == 3


def test_scheduler_preserves_minimum_per_block_interval_without_request_gap(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=4, delay=0.0)
    collector.run()

    assert collector.state == "completed"
    assert len(client.starts) == 4
    assert client.starts[1][1] - client.ends[0] < 10.0
    first_start = client.starts[0][1]
    repeated_start = client.starts[3][1]
    assert repeated_start - first_start >= 60.0


def test_variable_reservation_latency_preserves_actual_read_interval(tmp_path, monkeypatch):
    collector, client, clock = make_collector(tmp_path, limit=4)
    save_state = collector.store.save_collector_state

    def delayed_first_reservation(state, updated_at):
        if state.get("request_in_flight") and state["request_count"] == 1:
            clock.elapsed += 0.5
        save_state(state, updated_at)

    monkeypatch.setattr(collector.store, "save_collector_state", delayed_first_reservation)
    collector.run()

    assert collector.state == "completed"
    assert [offset for offset, _ in client.starts] == [4102, 28688, 36864, 4102]
    assert client.starts[3][1] - client.starts[0][1] >= 60.0


def test_duration_limit_stops_before_next_request(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=None, duration=15.0, delay=8.0)
    collector.run()

    assert collector.state == "completed"
    assert [offset for offset, _ in client.starts] == [4102, 28688]


def test_finite_request_budget_stops_on_first_transport_error_without_retry(tmp_path):
    collector, client, _ = make_collector(
        tmp_path, limit=3, retry_on_transport_error=False
    )
    calls = []

    def fail_once(block):
        calls.append(block.offset)
        raise ModbusConnectionError("synthetic disconnect")

    client.read = fail_once
    collector.run()

    assert calls == [4102]
    assert collector.state == "stopped_transport"
    assert collector.status()["reason"] == "Endlicher Lauf wegen Transportfehler beendet"
    assert collector.store.get_collector_state()["request_count"] == 1

def test_completed_finite_run_does_not_resume_after_restart(tmp_path):
    first, _, _ = make_collector(tmp_path, limit=1)
    first.run()
    restored, client, _ = make_collector(tmp_path, limit=None, store=first.store)

    restored.start()

    assert restored.state == "completed"
    assert client.starts == []

def test_second_owner_for_same_deployment_is_rejected(tmp_path):
    first = DeviceLock(tmp_path / "collector.lock")
    second = DeviceLock(tmp_path / "collector.lock")
    first.acquire()
    try:
        with pytest.raises(DeviceOwnershipError, match="lock is held"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_pause_prevents_following_read_and_shutdown_wakes_paused_collector(tmp_path):
    clock = FakeClock()

    class GatedClient(FakeClient):
        def __init__(self):
            super().__init__(clock)
            self.entered = threading.Event()
            self.release = threading.Event()

        def read(self, block):
            self.starts.append((block.offset, clock.monotonic()))
            self.entered.set()
            assert self.release.wait(1)
            self.ends.append(clock.monotonic())
            return RegisterRead(block.offset, self.VALUES[block.offset])

    client = GatedClient()
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=SQLiteStore(tmp_path / "paused.sqlite3"),
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    collector.start()
    assert client.entered.wait(1)
    collector.pause()
    contender = DeviceLock(tmp_path / "collector.lock")
    with pytest.raises(DeviceOwnershipError):
        contender.acquire()
    client.release.set()
    deadline = time.monotonic() + 1
    while collector.state != "paused" and time.monotonic() < deadline:
        time.sleep(0.001)

    assert collector.state == "paused"
    assert len(client.starts) == 1
    collector.stop()
    contender.acquire()
    contender.release()


def test_shutdown_waits_for_inflight_read_then_prevents_another_request(tmp_path):
    clock = FakeClock()

    class GatedClient(FakeClient):
        def __init__(self):
            super().__init__(clock)
            self.entered = threading.Event()
            self.release = threading.Event()

        def read(self, block):
            self.starts.append((block.offset, clock.monotonic()))
            self.entered.set()
            assert self.release.wait(1)
            self.ends.append(clock.monotonic())
            return RegisterRead(block.offset, self.VALUES[block.offset])

    client = GatedClient()
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=SQLiteStore(tmp_path / "shutdown.sqlite3"),
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    with collector.mode_lock:
        collector.start()
        assert client.entered.wait(1)
        with pytest.raises(DeviceOwnershipError, match="lock is held"):
            collector.run()
        assert len(client.starts) == 1
        assert collector._request_in_flight
        with pytest.raises(TimeoutError, match="did not stop"):
            collector.stop(timeout=0.01)
        contender = DeviceLock(tmp_path / "collector.lock")
        with pytest.raises(DeviceOwnershipError):
            contender.acquire()
        client.release.set()
        collector.stop(timeout=1)
    contender.acquire()
    contender.release()

    assert len(client.starts) == 1


def test_counter_regression_stops_collector_without_rewriting_the_value(tmp_path):
    clock = FakeClock()

    class RegressingClient(FakeClient):
        def __init__(self):
            super().__init__(clock)
            self.counter_reads = 0

        def read(self, block):
            if block.offset == 28688:
                self.starts.append((block.offset, clock.monotonic()))
                self.counter_reads += 1
                self.ends.append(clock.monotonic())
                return RegisterRead(block.offset, (0, 2 if self.counter_reads == 1 else 1))
            return super().read(block)

    client = RegressingClient()
    store = SQLiteStore(tmp_path / "counter.sqlite3")
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
        max_requests=5,
    )
    collector.run()

    assert collector.state == "stopped_data"
    assert len(client.starts) == 5
    assert [row["value"] for row in store.history("boiler.operating_minutes")] == [2]


def test_storage_failure_stops_without_another_read(tmp_path):
    class BrokenStore(SQLiteStore):
        def record_cycle(self, request, observations):
            raise StorageError("synthetic disk failure")

    collector, client, _ = make_collector(
        tmp_path, limit=3, store=BrokenStore(tmp_path / "broken.sqlite3")
    )
    collector.run()

    assert collector.state == "stopped_storage"
    assert len(client.starts) == 1
    assert "synthetic disk failure" in collector.error


def test_connection_failure_retries_the_same_block_after_delay(tmp_path):
    clock = FakeClock()

    class RecoversOnRetry(FakeClient):
        def read(self, block):
            if not self.starts:
                self.starts.append((block.offset, clock.monotonic()))
                clock.origin += timedelta(days=1)
                raise ModbusConnectionError("synthetic offline")
            return super().read(block)

    client = RecoversOnRetry(clock)
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=SQLiteStore(tmp_path / "recovery.sqlite3"),
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
        max_requests=2,
    )
    collector.run()

    assert [offset for offset, _ in client.starts] == [4102, 4102]
    assert client.starts[1][1] - client.starts[0][1] >= 60
    assert collector.state == "completed"
    assert collector.status()["reconnect_attempts"] == 1


def test_reconnect_budget_stops_after_exactly_five_attempts(tmp_path):
    clock = FakeClock()

    class AlwaysOffline(FakeClient):
        def read(self, block):
            self.starts.append((block.offset, clock.monotonic()))
            raise ModbusConnectionError("synthetic offline")

    client = AlwaysOffline(clock)
    store = SQLiteStore(tmp_path / "budget.sqlite3")
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    collector.run()

    assert len(client.starts) == 6  # Initial failure plus the five reserved retries.
    assert collector.state == "stopped_transport"
    assert collector.status()["reconnect_attempts"] == 5
    restored, restored_client, _ = make_collector(
        tmp_path, store=store, limit=2
    )
    restored.start()
    assert restored.state == "stopped_transport"
    assert restored_client.starts == []


@pytest.mark.parametrize(
    "failure",
    [
        ProtocolError("synthetic malformed response"),
        IncompleteResponseError("synthetic partial response"),
    ],
)
def test_protocol_failure_stops_without_retry_or_next_block(tmp_path, failure):
    clock = FakeClock()

    class BadProtocol(FakeClient):
        def read(self, block):
            self.starts.append((block.offset, clock.monotonic()))
            raise failure

    client = BadProtocol(clock)
    store = SQLiteStore(tmp_path / "protocol.sqlite3")
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    collector.run()

    assert collector.state == "stopped_protocol"
    assert [offset for offset, _ in client.starts] == [4102]
    restarted_client = FakeClient(clock)
    restarted = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=restarted_client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    restarted.start()

    assert restarted.state == "stopped_protocol"
    assert restarted_client.starts == []


def test_restart_from_running_reserves_request_and_waits_conservatively(tmp_path):
    clock = FakeClock()
    store = SQLiteStore(tmp_path / "crash.sqlite3")
    original = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=FakeClient(clock),
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    original.state = "running"
    original._request_in_flight = True
    original._last_action = "Reserved request"
    original._persist_state()

    restarted = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=FakeClient(clock),
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )

    assert restarted.state == "reconnect_wait"
    assert restarted._retry_at == clock.now() + timedelta(seconds=60)
    assert restarted.status()["reconnect_attempts"] == 1


def test_midcycle_failure_requires_three_complete_cycles_to_clear_budget(tmp_path):
    clock = FakeClock()

    class DisconnectsAtOperatingCounter(FakeClient):
        def read(self, block):
            self.starts.append((block.offset, clock.monotonic()))
            if block.offset == 28688 and len(self.starts) == 2:
                raise ModbusConnectionError("synthetic offline")
            clock.elapsed += self.delay
            self.ends.append(clock.monotonic())
            return RegisterRead(block.offset, self.VALUES[block.offset])

    client = DisconnectsAtOperatingCounter(clock)
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=SQLiteStore(tmp_path / "three-cycles.sqlite3"),
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
        max_requests=13,
    )
    collector.run()

    assert len(client.starts) == 13
    assert collector.state == "completed"
    assert collector.status()["reconnect_attempts"] == 0
    assert collector._successful_core_cycles == 0


def test_user_pause_is_persisted_and_does_not_autostart_after_restart(tmp_path):
    clock = FakeClock()
    store = SQLiteStore(tmp_path / "pause.sqlite3")
    collector = Collector(
        host="unused.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=FakeClient(clock),
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    collector.state = "running"
    collector.pause()

    restored, client, _ = make_collector(tmp_path, store=store, limit=2)
    restored.start()

    assert restored.state == "paused"
    assert client.starts == []


def test_changed_target_cannot_resume_saved_retry_state(tmp_path):
    clock = FakeClock()
    store = SQLiteStore(tmp_path / "target-change.sqlite3")
    original = Collector(
        host="first.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=FakeClient(clock),
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    original.state = "reconnect_wait"
    original.error = "synthetic connection failure"
    original._retry_at = clock.now() + timedelta(seconds=60)
    original._retry_delay_seconds = 60
    original._retry_monotonic_deadline = clock.monotonic() + 60
    original._persist_state()

    client = FakeClient(clock)
    restarted = Collector(
        host="second.invalid",
        port=502,
        store=store,
        data_dir=tmp_path,
        client=client,
        monotonic=clock.monotonic,
        wait=clock.wait,
        now=clock.now,
    )
    restarted.start()

    assert restarted.state == "paused"
    assert restarted.error == "Saved state belongs to a different target or profile"
    assert client.starts == []


@pytest.mark.parametrize("action", ["start", "run", "resume", "acknowledge_and_start"])
@pytest.mark.parametrize(
    "diagnostic_state",
    [
        "running", "awaiting_review", "interrupted", "stopped_transport",
        "stopped_protocol", "stopped_data", "stopped_storage",
    ],
)
def test_diagnostic_blocker_survives_restart_without_collector_mutation(
    tmp_path, action, diagnostic_state,
):
    original, _, _ = make_collector(tmp_path)
    original.error = "Synthetischer Kernfehler"
    original._request_count = 7
    original._reconnect_attempts = 3
    original._successful_core_cycles = 1
    original._successful_blocks_in_cycle = 2
    original._persist_state()
    run_id = diagnostic_run(original.store, diagnostic_state)
    collector, client, _ = make_collector(tmp_path, store=original.store)
    collector._stop.set()
    collector._wake.set()
    before_fields = collector.__dict__.copy()
    before_state = collector.store.get_collector_state()
    before_run = collector.store.get_diagnostic_run(run_id)

    with pytest.raises(CollectorStopped, match="diagnostic"):
        getattr(collector, action)()

    assert collector.__dict__ == before_fields
    assert collector._stop.is_set()
    assert collector._wake.is_set()
    assert collector._paused.is_set()
    assert collector.store.get_collector_state() == before_state
    assert collector.store.get_diagnostic_run(run_id) == before_run
    assert client.starts == []
    contender = DeviceLock(tmp_path / "collector.lock")
    contender.acquire()
    contender.release()


@pytest.mark.parametrize("action", ["start", "run"])
def test_diagnostic_blocker_is_checked_under_os_ownership(tmp_path, monkeypatch, action):
    collector, client, _ = make_collector(tmp_path)
    contender = DeviceLock(tmp_path / "collector.lock")

    def blocker():
        with pytest.raises(DeviceOwnershipError):
            contender.acquire()
        return "synthetic-blocker"

    monkeypatch.setattr(collector.store, "diagnostic_access_blocker", blocker)
    with pytest.raises(CollectorStopped, match="diagnostic"):
        getattr(collector, action)()

    assert collector.state == "paused"
    assert collector.store.get_collector_state() is None
    assert client.starts == []
    contender.acquire()
    contender.release()


@pytest.mark.parametrize(
    ("history", "recovery_delay", "first_delay"),
    [
        (True, None, 60.0),
        (False, None, 0.0),
        (True, -10.0, 60.0),
        (True, 10.0, 60.0),
        (True, 90.0, 90.0),
        (False, -10.0, 0.0),
        (False, 10.0, 10.0),
    ],
)
def test_diagnostic_history_delays_first_read_in_normal_and_recovery_paths(
    tmp_path, history, recovery_delay, first_delay,
):
    collector, client, clock = make_collector(tmp_path, limit=1)
    diagnostic_run(
        collector.store, "cancelled" if history else "planned",
        reserve_request=history,
    )
    clock.elapsed = 100.0
    if recovery_delay is not None:
        collector.state = "reconnect_wait"
        collector._retry_at = clock.now() + timedelta(seconds=recovery_delay)
        collector._retry_monotonic_deadline = clock.monotonic() + recovery_delay
        collector._retry_delay_seconds = 60.0
    waits = []

    def boundary_wait(event, seconds):
        assert not event.is_set()
        assert client.starts == []
        waits.append(seconds)
        if len(waits) == 1:
            assert seconds == pytest.approx(first_delay)
            clock.elapsed += seconds - 0.001
        else:
            assert seconds == pytest.approx(0.001)
            clock.elapsed += seconds
        return False

    collector.wait = boundary_wait
    collector.run()

    assert collector.state == "completed"
    assert client.starts == [(4102, pytest.approx(100.0 + first_delay))]
    assert len(waits) == (2 if first_delay else 0)


def test_acknowledged_diagnostic_error_stays_terminal_until_explicit_collector_resume(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=1)
    run_id = diagnostic_run(collector.store, "stopped_data")
    with pytest.raises(CollectorStopped):
        collector.acknowledge_and_start()

    collector.store.acknowledge_diagnostic_run(run_id, "Synthetische Ursache geprüft")
    assert client.starts == []
    assert collector.store.get_diagnostic_run(run_id)["state"] == "stopped_data"
    collector.resume()
    collector._thread.join(1)

    assert not collector._thread.is_alive()
    assert collector.state == "completed"
    assert client.starts == [(4102, 60.0)]
    collector.stop()


def test_collector_rejects_actual_competing_process_without_client_access(tmp_path):
    code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from backend.device_lock import DeviceLock\n"
        "lock = DeviceLock(Path(sys.argv[1]) / 'collector.lock')\n"
        "lock.acquire()\n"
        "print('owned', flush=True)\n"
        "try:\n"
        "    sys.stdin.readline()\n"
        "finally:\n"
        "    lock.release()\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    collector, client, _ = make_collector(tmp_path)
    try:
        assert process.stdout.readline().strip() == "owned"
        for action in (collector.start, collector.run):
            with pytest.raises(DeviceOwnershipError, match="lock is held"):
                action()
        assert client.starts == []
        assert collector.store.get_collector_state() is None
    finally:
        try:
            _, stderr = process.communicate("\n", timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
            raise
    assert process.returncode == 0, stderr
    collector._lock.acquire()
    collector._lock.release()
