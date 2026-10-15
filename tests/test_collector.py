from datetime import datetime, timedelta, timezone
import threading
import time

import pytest

from backend.collector import Collector, CollectorOwnershipError, _ProcessLock
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


def make_collector(tmp_path, *, limit=3, duration=None, delay=0.0, store=None):
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


def test_duration_limit_stops_before_next_request(tmp_path):
    collector, client, _ = make_collector(tmp_path, limit=None, duration=15.0, delay=8.0)
    collector.run()

    assert collector.state == "completed"
    assert [offset for offset, _ in client.starts] == [4102, 28688]


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
