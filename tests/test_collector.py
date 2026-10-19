from datetime import datetime, timedelta, timezone
import threading
import time

import pytest

from backend.collector import Collector, CollectorOwnershipError, _ProcessLock
from backend.logging_config import merge_csv
from backend.modbus import (
    ConnectionError as ModbusConnectionError,
    IncompleteResponseError,
    ModbusExceptionError,
    ProtocolError,
    RegisterRead,
)
from backend.storage import SQLiteStore, StorageError
from backend.modbus_simulator import ModbusSimulator, _SYNTHETIC_WORDS
from backend.modbus import ModbusTcpClient
from backend.registers import READ_PROFILE, REGISTER_DEFINITIONS, decode_register_block


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
    assert collector.store.get_collector_state()["request_count"] == 1

def test_completed_finite_run_does_not_resume_after_restart(tmp_path):
    first, _, _ = make_collector(tmp_path, limit=1)
    first.run()
    restored, client, _ = make_collector(tmp_path, limit=None, store=first.store)

    restored.start()

    assert restored.state == "completed"
    assert client.starts == []

def test_second_owner_for_same_deployment_is_rejected(tmp_path):
    first = _ProcessLock(tmp_path / "collector.lock")
    second = _ProcessLock(tmp_path / "collector.lock")
    first.acquire()
    try:
        with pytest.raises(CollectorOwnershipError, match="lock is held"):
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
    client.release.set()
    deadline = time.monotonic() + 1
    while collector.state != "paused" and time.monotonic() < deadline:
        time.sleep(0.001)

    assert collector.state == "paused"
    assert len(client.starts) == 1
    collector.stop()


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
    collector.start()
    assert client.entered.wait(1)
    with pytest.raises(TimeoutError, match="did not stop"):
        collector.stop(timeout=0.01)
    client.release.set()
    collector.stop(timeout=1)

    assert len(client.starts) == 1


def test_counter_regression_records_invalid_and_continues_other_signals(tmp_path):
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
        max_requests=9,
    )
    collector.run()

    assert collector.state == "completed"
    assert len(client.starts) == 9
    rows = store.history("boiler.operating_minutes")
    assert [row["value"] for row in rows] == [2, None]
    assert rows[-1]["quality"] == "invalid"
    assert rows[-1]["error_code"] == "invalid_counter_regression"
    assert collector.blocked_signals == {"boiler.operating_minutes"}
    assert client.counter_reads == 2


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
    assert collector.error == "Speicherzugriff fehlgeschlagen; Erfassung angehalten."


def test_connection_failure_keeps_other_reads_and_retries_at_normal_interval(tmp_path):
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
        max_requests=4,
    )
    collector.run()

    assert [offset for offset, _ in client.starts] == [4102, 28688, 36864, 4102]
    assert client.starts[3][1] - client.starts[0][1] == 60
    assert collector.state == "completed"
    assert collector.error is None
    assert [(row["quality"], row["value"]) for row in collector.store.history("boiler.temperature")] == [
        ("unavailable", None), ("ok", 42),
    ]


@pytest.mark.parametrize("recover", [False, True])
def test_long_outage_has_no_attempt_limit_or_backoff(tmp_path, recover):
    collector, client, clock = make_collector(tmp_path, limit=24)
    read = client.read

    def offline_then_available(block):
        if not recover or len(client.starts) < 21:
            client.starts.append((block.offset, clock.monotonic()))
            raise ModbusConnectionError("synthetischer Ausfall")
        return read(block)

    client.read = offline_then_available
    collector.run()

    assert collector.state == "completed"
    for offset in (4102, 28688, 36864):
        assert [started for actual, started in client.starts if actual == offset] == list(range(0, 480, 60))
    rows = collector.store.history("boiler.temperature")
    assert [row["value"] for row in rows] == [None] * 7 + ([42] if recover else [None])
    assert collector.status()["reconnect_attempts"] == (0 if recover else 23)
    assert (collector.error is None) == recover


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
    observation, = store.history("boiler.temperature")
    assert observation["quality"] == "invalid"
    assert observation["error_code"] == "protocol_error"
    assert observation["raw_words"] == []
    assert "synthetic" not in observation["error_message"]
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
    assert restarted._due_at(restarted._block_by_offset(4102)) == 60
    restarted.max_requests = 3
    restarted.run()
    assert restarted.client.starts == [(28688, 0), (36864, 0), (4102, 60)]




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


def test_logging_selection_changes_only_at_cycle_boundary_and_keeps_history(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=5)
    read = client.read

    def save_during_first_read(block):
        result = read(block)
        if len(client.starts) == 1:
            snapshot = collector.store.get_logging_config()
            for entry in snapshot["entries"]:
                if entry["signal_id"] in {"boiler.temperature", "buffer.bottom_temperature"}:
                    entry["record"] = False
            collector.store.save_logging_config(snapshot["revision"], snapshot["entries"])
            assert collector.logging_status()["apply_status"] == "ausstehend"
        return result

    client.read = save_during_first_read
    collector.run()

    assert [offset for offset, _ in client.starts] == [4102, 28688, 36864, 28688, 36864]
    assert collector.store.count_observations(signal_id="boiler.temperature") == 1
    assert collector.store.count_observations(signal_id="buffer.bottom_temperature") == 1
    assert collector.store.count_observations(signal_id="buffer.top_temperature") == 2
    assert collector.store.count_observations(signal_id="boiler.operating_minutes") == 2
    assert collector.store.history("buffer.bottom_temperature")[0]["value"] == 20
    assert collector.logging_status()["active_revision"] == 1
    assert collector.logging_status()["apply_status"] == "aktiv"


def test_empty_logging_selection_waits_without_reads_and_can_be_replaced(tmp_path):
    collector, client, clock = make_collector(tmp_path, limit=1, duration=2)
    snapshot = collector.store.get_logging_config()
    for entry in snapshot["entries"]:
        entry["record"] = False
    collector.store.save_logging_config(0, snapshot["entries"])
    wait = clock.wait

    def enable_buffer_after_idle(event, seconds):
        result = wait(event, seconds)
        if clock.elapsed >= 0.5 and collector.store.get_logging_config()["revision"] == 1:
            assert client.starts == []
            saved = collector.store.get_logging_config()
            next(entry for entry in saved["entries"] if entry["code"] == "9000")["record"] = True
            collector.store.save_logging_config(1, saved["entries"])
        return result

    collector.wait = enable_buffer_after_idle
    collector.run()

    assert client.starts == [(36864, 0.5)]
    assert collector.store.count_observations() == 1
    assert collector.store.history("buffer.top_temperature")[0]["value"] == 30
    assert collector.state == "completed"


def test_save_during_connection_failure_applies_at_next_cycle_boundary(tmp_path):
    collector, client, clock = make_collector(tmp_path, limit=5)
    read = client.read
    attempts = []

    def fail_and_change_selection(block):
        attempts.append((block.offset, clock.elapsed))
        if len(attempts) == 1:
            snapshot = collector.store.get_logging_config()
            for entry in snapshot["entries"]:
                entry["record"] = entry["code"] == "9000"
            collector.store.save_logging_config(0, snapshot["entries"])
            raise ModbusConnectionError("synthetischer Verbindungsfehler")
        return read(block)

    client.read = fail_and_change_selection
    collector.run()

    assert [offset for offset, _ in attempts] == [4102, 28688, 36864, 36864, 36864]
    assert [at for offset, at in attempts if offset == 36864] == [0, 60, 120]
    assert collector.status()["reconnect_attempts"] == 0
    assert collector.logging_status()["active_revision"] == 1
    assert [(row["quality"], row["value"]) for row in collector.store.history("boiler.temperature")] == [
        ("unavailable", None),
    ]
    assert collector.store.count_observations(signal_id="buffer.bottom_temperature") == 1
    assert collector.store.count_observations(signal_id="buffer.top_temperature") == 3


def extended_collector(tmp_path, *, limit=None, duration=None):
    collector, client, clock = make_collector(tmp_path, limit=limit, duration=duration)
    client.VALUES = {
        block.offset: tuple(
            _SYNTHETIC_WORDS[offset] for offset in range(block.offset, block.offset + block.count)
        )
        for block in READ_PROFILE
    }
    client.VALUES.update(FakeClient.VALUES)
    return collector, client, clock


def select_extended(collector, codes, *, keep_core=True):
    snapshot = collector.store.get_logging_config()
    rows = "\n".join(
        f'{REGISTER_DEFINITIONS[code]["name"]};{REGISTER_DEFINITIONS[code]["offset"]};{code}'
        for code in codes
    )
    entries = merge_csv(snapshot["entries"], rows)
    for entry in entries:
        entry["record"] = entry["code"] in codes or (keep_core and entry["record"])
    collector.store.save_logging_config(snapshot["revision"], entries)


def test_selected_extensions_record_decoded_values_without_reading_unselected_words(tmp_path):
    collector, client, _ = extended_collector(tmp_path, limit=2)
    select_extended(collector, ("7012", "7013", "100A", "1003"), keep_core=False)
    snapshot = collector.store.get_logging_config()
    next(entry for entry in snapshot["entries"] if entry["code"] == "1003")["record"] = False
    collector.store.save_logging_config(snapshot["revision"], snapshot["entries"])

    collector.run()

    assert collector.state == "completed"
    assert [offset for offset, _ in client.starts] == [0x7012, 0x100A]
    supply = collector.store.history("modbus.100A")
    assert [(row["value"], row["raw_words"], row["unit"]) for row in supply] == [(24.0, [240], "V")]
    assert supply[0]["profile_id"] == "extended"
    assert collector.store.history("stoker.operating_minutes")[0]["value"] == 1560
    assert collector.store.history("modbus.1003") == []
    assert collector.store.history("boiler.temperature") == []


def test_extension_interval_does_not_displace_sixty_second_core_cadence(tmp_path):
    collector, client, _ = extended_collector(tmp_path, duration=660)
    select_extended(collector, ("100A",))

    collector.run()

    assert collector.state == "completed"
    assert [started for offset, started in client.starts if offset == 0x100A] == [0, 300, 600]
    for offset in (4102, 28688, 36864):
        assert [started for actual, started in client.starts if actual == offset] == list(range(0, 660, 60))


def test_extension_interval_starts_after_completed_read_not_scheduled_start(tmp_path):
    collector, client, _ = extended_collector(tmp_path, limit=2)
    client.delay = 7
    select_extended(collector, ("100A",), keep_core=False)

    collector.run()

    assert client.starts == [(0x100A, 0), (0x100A, 307)]


def test_save_during_extended_read_waits_for_full_profile_boundary(tmp_path):
    collector, client, _ = extended_collector(tmp_path, limit=4)
    select_extended(collector, ("1003", "100A"), keep_core=False)
    read = client.read

    def change_after_first_extension(block):
        reply = read(block)
        if len(client.starts) == 1:
            snapshot = collector.store.get_logging_config()
            next(entry for entry in snapshot["entries"] if entry["code"] == "100A")["record"] = False
            collector.store.save_logging_config(snapshot["revision"], snapshot["entries"])
            assert collector.logging_status()["apply_status"] == "ausstehend"
        return reply

    client.read = change_after_first_extension
    collector.run()

    assert [offset for offset, _ in client.starts] == [0x1003, 0x100A, 0x1003, 0x1003]
    assert collector.store.count_observations(signal_id="modbus.100A") == 1
    assert collector.logging_status()["active_revision"] == 2




@pytest.mark.parametrize("codes", [("100A",), ("1100",), ("7012", "7013")])
def test_extension_connection_failure_continues_at_normal_interval(tmp_path, codes):
    collector, client, _ = extended_collector(tmp_path, limit=8)
    select_extended(collector, codes, keep_core=False)

    def fail(block):
        client.starts.append((block.offset, client.clock.monotonic()))
        raise ModbusConnectionError("synthetischer Ausfall")

    client.read = fail
    collector.run()

    assert client.starts == [(int(codes[0], 16), at) for at in range(0, 2400, 300)]
    assert collector.state == "completed"
    assert collector.status()["reconnect_attempts"] == 7
    observation, = collector.store.current_signals()
    assert observation["quality"] == "unavailable"
    assert observation["value"] is None
    assert observation["error_code"] == "transport_error"
    assert observation["raw_words"] == []


def test_extension_outage_does_not_delay_core_reads(tmp_path):
    collector, client, clock = extended_collector(tmp_path, duration=660)
    select_extended(collector, ("100A",))
    read = client.read

    def fail_extension(block):
        if block.offset == 0x100A:
            client.starts.append((block.offset, clock.monotonic()))
            raise ModbusConnectionError("synthetischer Zusatzregister-Ausfall")
        return read(block)

    client.read = fail_extension
    collector.run()

    assert [at for offset, at in client.starts if offset == 0x100A] == [0, 300, 600]
    for offset in (4102, 28688, 36864):
        assert [at for actual, at in client.starts if actual == offset] == list(range(0, 660, 60))


@pytest.mark.parametrize("failure_type", [ModbusConnectionError, ProtocolError, IncompleteResponseError])
def test_read_to_clear_failure_stops_without_retry(tmp_path, failure_type):
    code = "85E0"
    collector, client, _ = extended_collector(tmp_path)
    select_extended(collector, (code,), keep_core=False)

    def fail(block):
        client.starts.append((block.offset, client.clock.monotonic()))
        raise failure_type("synthetischer ungewisser Ausleseausgang")

    client.read = fail
    collector.run()

    assert client.starts == [(int(code, 16), 0)]
    expected_state = "stopped_transport" if failure_type is ModbusConnectionError else "stopped_protocol"
    assert collector.state == expected_state
    assert collector.status()["reconnect_attempts"] == 0
    assert collector.status()["next_action_at"] is None
    observation, = collector.store.current_signals()
    assert observation["quality"] != "ok"
    assert observation["value"] is None
    assert observation["raw_words"] == []
    restarted, restarted_client, _ = make_collector(tmp_path, store=collector.store, limit=None)
    restarted.start()
    assert restarted.state == expected_state
    assert restarted_client.starts == []


@pytest.mark.parametrize("offset", [0x85E0])
@pytest.mark.parametrize(
    ("state", "in_flight", "retry_delay"),
    [
        ("running", True, None),
        ("reconnect_wait", False, 60),
        ("paused", True, None),
        ("paused", False, 60),
    ],
)
def test_uncertain_read_to_clear_request_cannot_resume_after_restart(
    tmp_path, offset, state, in_flight, retry_delay
):
    collector, _, _ = extended_collector(tmp_path)
    collector.state = state
    collector._request_in_flight = in_flight
    collector._retry_block_offset = offset if in_flight or retry_delay else 4102
    collector._next_offset = offset
    collector._request_count = 7
    collector._reconnect_attempts = 2
    collector._persist_state()
    saved = collector.store.get_collector_state()
    saved["retry_delay_seconds"] = retry_delay
    collector.store.save_collector_state(saved, collector.now().isoformat())

    restarted, client, _ = make_collector(tmp_path, store=collector.store, limit=None)
    restarted.start()

    assert restarted.state == "stopped_transport"
    assert restarted.status()["reconnect_attempts"] == 2
    assert restarted.status()["next_action_at"] is None
    assert restarted._request_count == 7
    assert client.starts == []


def test_extended_completion_and_offsets_restore_without_losing_interval_or_budget(tmp_path):
    collector, _, clock = extended_collector(tmp_path)
    collector._next_offset = 0x100A
    collector._retry_block_offset = 0x100A
    collector._last_completed[0x100A] = clock.monotonic()
    collector._last_completed_at[0x100A] = clock.now()
    collector._reconnect_attempts = 2
    collector._request_count = 7
    collector._persist_state()
    clock.elapsed = 30

    restarted = Collector(
        host="unused.invalid", port=502, store=collector.store, data_dir=tmp_path,
        client=FakeClient(clock), monotonic=clock.monotonic, wait=clock.wait, now=clock.now,
    )

    assert restarted.state == "paused"
    assert restarted._next_offset == restarted._retry_block_offset == 0x100A
    assert restarted._request_count == 7
    assert restarted.status()["reconnect_attempts"] == 2
    assert restarted._due_at(restarted._block_by_offset(0x100A)) - clock.monotonic() == 270


@pytest.mark.parametrize("offset", [0x100B, 0x7013])
def test_restore_rejects_unknown_or_nonblock_offsets(tmp_path, offset):
    collector, _, _ = extended_collector(tmp_path)
    collector._next_offset = offset
    collector._persist_state()

    restarted, client, _ = make_collector(tmp_path, store=collector.store, limit=None)
    restarted.start()

    assert restarted.state == "stopped_storage"
    assert client.starts == []


def test_stoker_counter_only_requires_valid_word_pair_not_boiler_uptime_progression(tmp_path):
    collector, client, _ = extended_collector(tmp_path, limit=2)
    select_extended(collector, ("7012", "7013"), keep_core=False)
    read = client.read

    def reset_stoker_after_first_read(block):
        result = read(block)
        client.VALUES[0x7012] = (0, 2)
        return result

    client.read = reset_stoker_after_first_read
    collector.run()

    assert collector.state == "completed"
    assert [row["value"] for row in collector.store.history("stoker.operating_minutes")] == [1560, 2]


def test_stoker_invalid_remaining_minutes_records_error_and_blocks_signal(tmp_path):
    collector, client, _ = extended_collector(tmp_path, limit=1)
    select_extended(collector, ("7012", "7013"), keep_core=False)
    client.VALUES[0x7012] = (1, 1440)

    collector.run()

    assert collector.state == "completed"
    signal, = collector.store.history("stoker.operating_minutes")
    assert signal["value"] is None
    assert signal["quality"] == "invalid"
    assert signal["error_code"] == "invalid_counter"
    assert signal["raw_words"] == [1, 1440]
    assert collector.blocked_signals == {"stoker.operating_minutes"}


def test_simulator_supports_the_explicit_read_profile_with_decodable_synthetic_values():
    seen_offsets = set()
    with ModbusSimulator() as simulator:
        client = ModbusTcpClient(*simulator.address)
        for block in READ_PROFILE:
            reply = client.read(block)
            assert len(reply.words) == block.count
            assert decode_register_block(reply.offset, reply.words)
            seen_offsets.update(range(block.offset, block.offset + block.count))
    assert seen_offsets == {definition["offset"] for definition in REGISTER_DEFINITIONS.values()}


def test_simulator_protocol_reads_clear_only_its_own_accumulator():
    block = next(block for block in READ_PROFILE if block.offset == 0x85E0)
    other = next(block for block in READ_PROFILE if block.offset == 0x85E1)
    with ModbusSimulator() as simulator:
        client = ModbusTcpClient(*simulator.address)
        assert client.read(block).words == (20,)
        assert client.read(block).words == (0,)
        assert client.read(other).words == (20,)
    with ModbusSimulator() as independent:
        assert ModbusTcpClient(*independent.address).read(block).words == (20,)


def test_weather_error_replaces_good_value_without_blocking_other_signals(tmp_path):
    collector, client, _ = extended_collector(tmp_path, duration=660)
    select_extended(collector, ("1020", "1021", "10D1"), keep_core=False)
    client.VALUES.update({0x1020: (20,), 0x1021: (0,), 0x10D1: (7,)})
    read = client.read

    def weather_disappears(block):
        reply = read(block)
        if block.offset == 0x10D1:
            client.VALUES[0x1020] = (65486,)
            client.VALUES[0x1021] = (65535,)
        return reply

    client.read = weather_disappears
    collector.run()

    assert collector.state == "completed"
    assert collector.blocked_signals == set()
    for code in ("1020", "1021"):
        rows = collector.store.history(f"modbus.{code}")
        assert rows[0]["quality"] == "ok"
        assert [row["quality"] for row in rows[1:]] == ["unavailable", "unavailable"]
        assert all(row["value"] is None for row in rows[1:])
        assert all(row["error_code"] == "missing_weather" for row in rows[1:])
    current = {row["signal_id"]: row for row in collector.store.current_signals()}
    assert current["modbus.1020"]["value"] is None
    assert current["modbus.10D1"]["value"] == 7
    assert [offset for offset, _ in client.starts] == [0x1020, 0x1021, 0x10D1] * 3
    events = [event for event in collector.store.events() if event["kind"] == "signal_quality_changed"]
    assert len(events) == 2


def test_invalid_buffer_channel_is_not_resaved_while_healthy_neighbor_continues(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=8)
    client.VALUES = {**FakeClient.VALUES, 36864: (110, 20)}
    collector.run()

    assert collector.state == "completed"
    assert collector.blocked_signals == {"buffer.top_temperature"}
    invalid, = collector.store.history("buffer.top_temperature")
    assert invalid["value"] is None
    assert invalid["error_code"] == "invalid_temperature"
    assert invalid["raw_words"] == [110, 20]
    assert len(collector.store.history("buffer.bottom_temperature")) == 2
    assert collector.store.get_collector_state()["blocked_signals"] == ["buffer.top_temperature"]
    collector.state = "running"
    collector.error = None
    assert collector.status()["blocked_signal_count"] == 1
    assert "ausgesetzt" in collector.status()["reason"]


@pytest.mark.parametrize("offset", [4102, 36864, 0x85E0])
def test_valid_exception_blocks_only_its_signals_and_survives_restart(tmp_path, monkeypatch, offset):
    collector, client, clock = extended_collector(tmp_path, duration=130)
    if offset == 0x85E0:
        select_extended(collector, ("85E0",))
    read = client.read

    def reject_block(block):
        if block.offset == offset:
            client.starts.append((offset, clock.monotonic()))
            raise ModbusExceptionError(2)
        return read(block)

    client.read = reject_block
    collector.run()

    block = collector._block_by_offset(offset)
    assert collector.blocked_signals == set(block.signal_ids)
    assert sum(actual == offset for actual, _ in client.starts) == 1
    assert any(actual != offset for actual, _ in client.starts)
    for signal_id in block.signal_ids:
        row, = collector.store.history(signal_id)
        assert row["error_code"] == "modbus_exception_2"
        assert row["value"] is None
        assert row["raw_words"] == []
    assert collector._retry_at is None
    collector.state = "paused"
    collector._persist_state()
    restored, restored_client, _ = make_collector(
        tmp_path, limit=None, duration=130, store=collector.store
    )
    assert restored.blocked_signals == set(block.signal_ids)
    monkeypatch.setattr(restored, "start", lambda: None)
    restored.resume()
    restored.run()
    assert all(actual != offset for actual, _ in restored_client.starts)
    assert restored.blocked_signals == set(block.signal_ids)
    count = restored._request_count
    restored.state = "paused"
    restored.acknowledge_and_start()
    assert restored.blocked_signals == set()
    assert restored._request_count == count


@pytest.mark.parametrize("failure", [
    ModbusExceptionError(2),
    "invalid_temperature",
])
def test_signal_failure_during_recovery_clears_retry_deadlines(tmp_path, failure):
    collector, client, clock = make_collector(tmp_path, limit=2)
    snapshot = collector.store.get_logging_config()
    for entry in snapshot["entries"]:
        entry["record"] = entry["code"] == "1006"
    collector.store.save_logging_config(snapshot["revision"], snapshot["entries"])
    calls = 0

    def recovering_failure(block):
        nonlocal calls
        calls += 1
        client.starts.append((block.offset, clock.monotonic()))
        if calls == 1:
            raise ModbusConnectionError("private-host.invalid /private/path")
        if isinstance(failure, ModbusExceptionError):
            raise failure
        return RegisterRead(block.offset, (110,))

    client.read = recovering_failure
    collector.run()
    assert collector.state == "completed"
    assert collector.blocked_signals == {"boiler.temperature"}
    assert collector._retry_at is None
    rows = collector.store.history("boiler.temperature")
    assert rows[0]["error_code"] == "transport_error"
    assert "private" not in rows[0]["error_message"]
    assert rows[-1]["quality"] == "invalid"


@pytest.mark.parametrize("blocked", [["unknown.signal"], ["boiler.temperature", "boiler.temperature"], "boiler.temperature", [123]])
def test_restore_rejects_invalid_blocked_ids(tmp_path, blocked):
    collector, _, _ = make_collector(tmp_path)
    collector._persist_state()
    saved = collector.store.get_collector_state()
    saved["blocked_signals"] = blocked
    collector.store.save_collector_state(saved, collector.now().isoformat())
    restored, client, _ = make_collector(tmp_path, store=collector.store)
    assert restored.state == "stopped_storage"
    restored.start()
    assert client.starts == []


def test_all_selected_signals_blocked_waits_without_reads_and_csv_does_not_unblock(tmp_path):
    collector, client, clock = extended_collector(tmp_path, duration=2)
    select_extended(collector, ("100A",), keep_core=False)
    collector.blocked_signals.add("modbus.100A")
    select_extended(collector, ("100A",), keep_core=False)
    waits = []
    wait = clock.wait

    def tracked_wait(event, seconds):
        waits.append(seconds)
        return wait(event, seconds)

    collector.wait = tracked_wait
    collector.run()
    assert collector.state == "completed"
    assert client.starts == []
    assert waits == [0.25] * 8
    assert collector.blocked_signals == {"modbus.100A"}


@pytest.mark.parametrize("words", [(42, 43), (True,)])
def test_structural_decoder_failure_is_global_and_records_known_raw_words(tmp_path, words):
    collector, client, _ = make_collector(tmp_path)
    client.VALUES = {**FakeClient.VALUES, 4102: words}
    collector.run()
    assert collector.state == "stopped_data"
    assert len(client.starts) == 1
    row, = collector.store.history("boiler.temperature")
    assert row["value"] is None
    assert row["quality"] == "invalid"
    assert row["raw_words"] == list(words)
    assert row["error_code"] in {"invalid_word_count", "invalid_register_word"}


def test_unselected_invalid_buffer_neighbor_is_not_quarantined_without_error_observation(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=2)
    snapshot = collector.store.get_logging_config()
    for entry in snapshot["entries"]:
        entry["record"] = entry["code"] == "9001"
    collector.store.save_logging_config(snapshot["revision"], snapshot["entries"])
    client.VALUES = {**FakeClient.VALUES, 36864: (110, 20)}
    collector.run()
    assert collector.state == "completed"
    assert collector.blocked_signals == set()
    assert collector.store.history("buffer.top_temperature") == []
    assert [(row["quality"], row["value"]) for row in collector.store.history("buffer.bottom_temperature")] == [
        ("ok", 20), ("ok", 20),
    ]


def test_modbus_device_failure_is_not_treated_as_an_isolated_bad_register(tmp_path):
    collector, client, _ = make_collector(tmp_path)

    def device_failure(block):
        client.starts.append((block.offset, client.clock.monotonic()))
        raise ModbusExceptionError(4)

    client.read = device_failure
    collector.run()
    assert collector.state == "stopped_protocol"
    assert len(client.starts) == 1
    assert collector.blocked_signals == set()
    failure, = collector.store.history("boiler.temperature")
    assert failure["value"] is None
    assert failure["error_code"] == "modbus_exception_4"


@pytest.mark.parametrize("code", ["1006", "100A"])
@pytest.mark.parametrize("state", ["stopped_transport", "reconnect_wait", "running"])
def test_restart_continues_after_old_budget_or_interrupted_request(tmp_path, code, state):
    original, _, clock = extended_collector(tmp_path)
    select_extended(original, (code,), keep_core=False)
    original.state = state
    original.error = "synthetischer alter Transportfehler"
    original._reconnect_attempts = 12
    original._request_count = 13
    original._request_in_flight = state == "running"
    original._retry_block_offset = original._next_offset = int(code, 16)
    original._persist_state()
    saved = original.store.get_collector_state()
    saved["retry_delay_seconds"] = 900
    saved["successful_core_cycles"] = 0
    saved["successful_blocks_in_cycle"] = 0
    original.store.save_collector_state(saved, clock.now().isoformat())

    restored, client, _ = extended_collector(tmp_path)
    read = client.read

    def stop_after_read(block):
        result = read(block)
        restored._stop.set()
        return result

    client.read = stop_after_read
    assert restored.state == "reconnect_wait"
    assert restored.status()["reconnect_attempts"] == 12
    restored.run()

    interval = 60 if code == "1006" else 300
    assert client.starts == [(int(code, 16), interval)]
    assert restored._request_count == 14
    assert restored.status()["reconnect_attempts"] == 0
    assert restored.error is None
    assert restored.store.current_signals()[0]["quality"] == "ok"


@pytest.mark.parametrize(("limit", "duration"), [(3, None), (None, 10)])
def test_old_finite_transport_stop_is_not_automatically_released(tmp_path, limit, duration):
    original, _, _ = make_collector(tmp_path, limit=limit, duration=duration)
    original.state = "stopped_transport"
    original._persist_state()
    restored, client, _ = make_collector(tmp_path, limit=None, store=original.store)
    restored.start()
    assert restored.state == "stopped_transport"
    assert client.starts == []


def test_pause_during_outage_survives_restart_and_resume_keeps_interval(tmp_path, monkeypatch):
    original, _, clock = make_collector(tmp_path, limit=None)
    select_extended(original, ("1006",), keep_core=False)
    original.state = "reconnect_wait"
    original.error = "synthetischer Ausfall"
    original._retry_at = clock.now() + timedelta(seconds=60)
    original._reconnect_attempts = 12
    original.pause()

    restored, client, _ = make_collector(tmp_path, limit=1, store=original.store)
    restored.start()
    assert restored.state == "paused"
    assert client.starts == []
    monkeypatch.setattr(restored, "start", lambda: None)
    restored.resume()
    restored.run()
    assert client.starts == [(4102, 60)]
    assert restored.state == "completed"
