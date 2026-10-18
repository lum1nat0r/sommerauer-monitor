from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.collector import Collector
from backend.config import Settings
from backend.main import app
from backend.modbus_simulator import ModbusSimulator


HEADERS = {"Origin": "http://testserver", "X-Requested-With": "SommerauerMonitor"}


class Clock:
    def __init__(self):
        self.seconds = 0.0
        self.origin = datetime(2026, 10, 18, tzinfo=timezone.utc)

    def monotonic(self):
        return self.seconds

    def now(self):
        return self.origin + timedelta(seconds=self.seconds)

    def wait(self, event, seconds):
        self.seconds += seconds
        return event.is_set()


def test_import_selection_simulator_history_and_metadata(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    with TestClient(app) as api, ModbusSimulator() as simulator:
        preview = api.post("/api/logging-config/preview", headers=HEADERS, json={
            "revision": 0,
            "csv_text": "Netzteil;4106;100A\nStoker_Tag;28690;7012\nStoker_Rest;28691;7013\nAusgangsbits;4848;12F0",
        })
        assert preview.status_code == 200
        entries = preview.json()["entries"]
        selected = {"100A", "7012", "7013", "12F0"}
        assert all(entry["record"] and entry["eligible"] for entry in entries if entry["code"] in selected)
        for entry in entries:
            entry["record"] = entry["code"] in selected
        saved = api.put("/api/logging-config", headers=HEADERS, json={"revision": 0, "entries": entries})
        assert saved.status_code == 200
        clock = Clock()
        collector = Collector(
            host=simulator.address[0], port=simulator.address[1],
            store=app.state.storage, data_dir=tmp_path, max_requests=3,
            max_duration_seconds=600, retry_on_transport_error=False,
            monotonic=clock.monotonic, now=clock.now, wait=clock.wait,
        )
        collector.run()
        assert collector.state == "completed"
        voltage = api.get("/api/history/modbus.100A").json()
        counter = api.get("/api/history/stoker.operating_minutes").json()
        protocol = api.get("/api/history/modbus.12F0").json()
        assert voltage["total"] == counter["total"] == protocol["total"] == 1
        assert voltage["items"][0]["value"] == voltage["items"][0]["raw_words"][0] / 10
        assert voltage["items"][0]["unit"] == "V"
        assert voltage["items"][0]["profile_id"] == "extended"
        assert api.get("/api/history/boiler.temperature").json()["total"] == 0
        metadata = api.get("/api/signals").json()
        protocol_definition = next(row for row in metadata["signals"] if row["signal_id"] == "modbus.12F0")
        assert protocol_definition["read_to_clear"] is True
        assert protocol_definition["live_confirmed"] is False
        assert api.get("/api/history/modbus.9020").status_code == 404
        assert {row["code"] for row in metadata["control_candidates"]} == {"9020", "9040"}


def test_legacy_unknown_import_becomes_selectable_without_auto_activation(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    with TestClient(app) as api:
        draft = api.post("/api/logging-config/preview", headers=HEADERS, json={
            "revision": 0, "csv_text": "Leistung;4099;1003",
        }).json()["entries"]
        row = next(row for row in draft if row["code"] == "1003")
        row["record"] = False
        row["signal_id"] = None
        row["unit"] = "Eigene Beschriftung"
        row["description"] = "Bleibt erhalten"
        result = api.put("/api/logging-config", headers=HEADERS, json={"revision": 0, "entries": draft})
        assert result.status_code == 200
        restored = next(row for row in result.json()["entries"] if row["code"] == "1003")
        assert restored["signal_id"] == "modbus.1003"
        assert restored["eligible"] is True
        assert restored["record"] is False
        assert restored["unit"] == "Eigene Beschriftung"
        assert restored["description"] == "Bleibt erhalten"


def test_freshness_respects_slow_extensions_instead_of_core_interval(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    with TestClient(app) as api:
        for signal_id, offset, value, unit, profile in (
            ("boiler.temperature", 4102, 42, "°C", "core"),
            ("modbus.100A", 4106, 24.5, "V", "extended"),
        ):
            app.state.storage.record_cycle(
                {"request_id": signal_id, "started_at": timestamp, "completed_at": timestamp,
                 "function_code": 3, "unit_id": 255, "offset": offset, "register_count": 1, "outcome": "ok"},
                [{"observation_id": signal_id, "signal_id": signal_id, "observed_at": timestamp,
                  "value": value, "unit": unit, "quality": "ok", "raw_words": [245] if profile == "extended" else [42],
                  "source": "synthetic", "profile_id": profile, "profile_version": "1", "decoder_version": "1"}],
            )
        current = {row["signal_id"]: row for row in api.get("/api/signals/current").json()["signals"]}
        assert current["boiler.temperature"]["fresh"] is False
        assert current["modbus.100A"]["fresh"] is True
        assert current["modbus.100A"]["value"] == 24.5
