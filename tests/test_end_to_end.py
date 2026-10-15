from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from threading import Event
import sqlite3

from fastapi.testclient import TestClient

from backend.collector import Collector
from backend.main import app
from backend.modbus import ModbusTcpClient
from backend.modbus_simulator import ModbusSimulator
from backend.storage import SQLiteStore


class VirtualClock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.started_at = datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return self.started_at + timedelta(seconds=self.elapsed)

    def wait(self, event: Event, seconds: float) -> bool:
        self.elapsed += seconds
        return event.is_set()


def test_simulator_collector_storage_api_and_csv_end_to_end(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.delenv("MODBUS_HOST", raising=False)
    from backend.config import get_settings

    get_settings.cache_clear()
    try:
        clock = VirtualClock()
        third_read = Event()

        with ModbusSimulator() as simulator:
            host, port = simulator.address
            transport = ModbusTcpClient(host, port)

            class ObservedClient:
                def __init__(self) -> None:
                    self.read_count = 0

                def read(self, block):
                    result = transport.read(block)
                    self.read_count += 1
                    if self.read_count == 3:
                        third_read.set()
                    return result

            store = SQLiteStore(data_dir / "monitor.sqlite3")
            collector = Collector(
                host=host,
                port=port,
                store=store,
                data_dir=data_dir,
                client=ObservedClient(),
                monotonic=clock.monotonic,
                wait=clock.wait,
                now=clock.now,
            )
            collector.start()
            assert third_read.wait(timeout=5), "collector did not read all three core blocks"
            collector.stop()

        with sqlite3.connect(store.path) as connection:
            requests = connection.execute(
                "SELECT function_code, unit_id, offset, register_count, started_at FROM requests ORDER BY started_at"
            ).fetchall()
            measurements_before = connection.execute(
                "SELECT observation_id, signal_id, observed_at, value, raw_words_json "
                "FROM observations ORDER BY observed_at, observation_id"
            ).fetchall()

        assert [row[:4] for row in requests] == [
            (3, 255, 4102, 1), (3, 255, 28688, 2), (3, 255, 36864, 2),
        ]
        request_starts = [datetime.fromisoformat(row[4]) for row in requests]
        assert all(
            (later - earlier).total_seconds() >= 10
            for earlier, later in zip(request_starts, request_starts[1:])
        )
        assert {row[1]: row[3] for row in measurements_before} == {
            "boiler.temperature": 42,
            "boiler.operating_minutes": 6079,
            "buffer.top_temperature": 47,
            "buffer.bottom_temperature": 38,
        }

        with TestClient(app) as client:
            current = client.get("/api/signals/current")
            history = client.get("/api/history/boiler.temperature")
            csv_response = client.get("/api/export.csv")
            status = client.get("/api/collector/status")

        assert current.status_code == history.status_code == csv_response.status_code == 200
        assert len(current.json()["signals"]) == 4
        boiler = next(item for item in current.json()["signals"] if item["signal_id"] == "boiler.temperature")
        assert (boiler["value"], boiler["quality"], boiler["fresh"]) == (42, "ok", True)
        assert history.json()["items"][0]["raw_words"] == [42]
        csv_rows = list(csv.DictReader(csv_response.text.splitlines()))
        assert len(csv_rows) == len(measurements_before) == 4
        assert [row["observation_id"] for row in csv_rows] == [row[0] for row in measurements_before]
        assert [row["observed_at"] for row in csv_rows] == [row[2] for row in measurements_before]
        assert all(row["quality"] == "ok" for row in csv_rows)
        assert status.json()["state"] == "paused"

        reopened = SQLiteStore(store.path)
        measurements_after = reopened.history_page("boiler.temperature", limit=1)
        assert reopened.count_observations() == len(measurements_before)
        assert measurements_after[0]["value"] == 42
    finally:
        get_settings.cache_clear()


def test_replaced_data_volume_exposes_empty_history_without_fabricated_values(tmp_path, monkeypatch) -> None:
    from backend.config import get_settings

    original = SQLiteStore(tmp_path / "original-volume" / "monitor.sqlite3")
    observed_at = datetime.now(timezone.utc).isoformat()
    original.record_cycle(
        {
            "request_id": "before-volume-loss",
            "started_at": observed_at,
            "completed_at": observed_at,
            "function_code": 3,
            "unit_id": 255,
            "offset": 4102,
            "register_count": 1,
            "outcome": "ok",
        },
        [{
            "observation_id": "before-volume-loss-observation",
            "signal_id": "boiler.temperature",
            "observed_at": observed_at,
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
    assert original.count_observations() == 1

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "replacement-volume"))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.delenv("MODBUS_HOST", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            health = client.get("/api/health").json()
            signals = client.get("/api/signals/current").json()["signals"]
            history = client.get("/api/history/boiler.temperature").json()
            status = client.get("/api/collector/status").json()

        assert health == {"status": "ok", "database": "ok"}
        assert signals == []
        assert history["total"] == 0 and history["items"] == []
        assert status["state"] == "unconfigured"
    finally:
        get_settings.cache_clear()
