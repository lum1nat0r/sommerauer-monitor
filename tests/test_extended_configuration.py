import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.collector import Collector
from backend.config import Settings
from backend.logging_config import default_entries, merge_csv, normalize_entries
from backend.main import app
from backend.modbus_simulator import ModbusSimulator
from backend.registers import REGISTER_DEFINITIONS, SIGNAL_DEFINITIONS, decode_register_block


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
        assert api.get("/api/history/modbus.9020").json()["total"] == 0
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


def test_new_percent_metadata_keeps_historical_observation_units_and_values(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    with TestClient(app) as api:
        decoded, = decode_register_block(0x1106, (37,))
        for index, unit in enumerate(("Rohwert", decoded.unit)):
            timestamp = f"2026-10-18T00:0{index}:00+00:00"
            app.state.storage.record_cycle(
                {"request_id": f"unit-{index}", "started_at": timestamp, "completed_at": timestamp,
                 "function_code": 3, "unit_id": 255, "offset": decoded.offset, "register_count": 1, "outcome": "ok"},
                [{"observation_id": f"unit-{index}", "signal_id": decoded.signal_id, "observed_at": timestamp,
                  "value": decoded.value, "unit": unit, "quality": decoded.quality, "raw_words": list(decoded.raw_words),
                  "source": "synthetic", "profile_id": "extended", "profile_version": "1", "decoder_version": "1"}],
            )
        metadata = {row["signal_id"]: row for row in api.get("/api/signals").json()["signals"]}
        assert metadata[decoded.signal_id]["unit"] == "%"
        assert metadata["buffer.bottom_temperature"]["module_status"] == "active"
        assert metadata["modbus.91E1"]["module_status"] == "inactive"
        assert metadata["modbus.91E1"]["verification_status"] == "operator_touch_confirmed"
        observations = api.get(f"/api/history/{decoded.signal_id}").json()["items"]
        assert [(row["value"], row["unit"], row["raw_words"]) for row in observations] == [
            (37, "Rohwert", [37]), (37, "%", [37]),
        ]
        current = {row["signal_id"]: row for row in api.get("/api/signals/current").json()["signals"]}
        assert (current[decoded.signal_id]["value"], current[decoded.signal_id]["unit"]) == (37, "%")
        exported = list(csv.DictReader(io.StringIO(api.get("/api/export.csv").text)))
        assert [(row["value"], row["unit"]) for row in exported] == [("37", "Rohwert"), ("37", "%")]


def test_display_metadata_does_not_change_import_identity_or_saved_selection():
    entries = merge_csv(default_entries(), "V1_Ist;4358;1106\nBO02_Ist;36865;9001")
    for entry in entries:
        if entry["code"] == "1106":
            entry["record"] = False
            entry["unit"] = "Bisherige Einheit"
    normalized = normalize_entries(entries)
    assert [(row["code"], row["name"], row["record"], row["unit"]) for row in normalized] == [
        (row["code"], row["name"], row["record"], row["unit"]) for row in entries
    ]
    reimported = merge_csv(normalized, "V1_Ist;4358;1106\nBO02_Ist;36865;9001")
    assert all(row["change"] == "unchanged" and row["changed_fields"] == [] for row in reimported)
    assert REGISTER_DEFINITIONS["1106"]["name"] == "V1_Ist"
    assert SIGNAL_DEFINITIONS["modbus.1106"]["label"] != "V1_Ist"


def test_status_requires_explicit_save_and_survives_loopback_and_error(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    with TestClient(app) as api, ModbusSimulator() as simulator:
        before = api.get("/api/logging-config").json()
        assert not any(row["code"] == "1001" for row in before["entries"])
        preview = api.post("/api/logging-config/preview", headers=HEADERS, json={
            "revision": 0, "csv_text": "Betriebsstatus;4097;1001",
        }).json()
        status = next(row for row in preview["entries"] if row["code"] == "1001")
        assert status["eligible"] and status["record"]
        assert api.get("/api/logging-config").json()["entries"] == before["entries"]
        wrong = api.post("/api/logging-config/preview", headers=HEADERS, json={
            "revision": 0, "csv_text": "Betriebsstatus;4098;1001",
        }).json()
        assert not next(row for row in wrong["entries"] if row["code"] == "1001")["eligible"]
        for row in preview["entries"]:
            row["record"] = row["code"] == "1001"
        assert api.put("/api/logging-config", headers=HEADERS, json={
            "revision": 0, "entries": preview["entries"],
        }).status_code == 200
        selected = [row["code"] for row in api.get("/api/logging-config").json()["entries"] if row["record"]]
        assert selected == ["1001"]
        clock = Clock()
        collector = Collector(
            host=simulator.address[0], port=simulator.address[1],
            store=app.state.storage, data_dir=tmp_path, max_requests=1,
            max_duration_seconds=10, retry_on_transport_error=False,
            monotonic=clock.monotonic, now=clock.now, wait=clock.wait,
        )
        collector.run()
        assert collector.state == "completed"
        point, = api.get("/api/history/modbus.1001").json()["items"]
        assert (point["value"], point["raw_words"], point["unit"]) == (2, [2], "Rohwert")
        current = {row["signal_id"]: row for row in api.get("/api/signals/current").json()["signals"]}
        assert current["modbus.1001"]["value"] == 2
        exported = list(csv.DictReader(io.StringIO(api.get("/api/export.csv").text)))
        assert [(row["signal_id"], row["value"]) for row in exported] == [("modbus.1001", "2")]
        invalid, = decode_register_block(4097, (0x8000,))
        timestamp = (clock.now() + timedelta(seconds=300)).isoformat()
        app.state.storage.record_cycle(
            {"request_id": "invalid-status", "started_at": timestamp, "completed_at": timestamp,
             "function_code": 3, "unit_id": 255, "offset": 4097, "register_count": 1, "outcome": "ok"},
            [{"observation_id": "invalid-status", "signal_id": invalid.signal_id, "observed_at": timestamp,
              "value": invalid.value, "unit": invalid.unit, "quality": invalid.quality,
              "raw_words": list(invalid.raw_words), "error_code": invalid.error_code,
              "error_message": invalid.error_message, "source": "synthetic",
              "profile_id": "extended", "profile_version": "1", "decoder_version": "1"}],
        )
        current = {row["signal_id"]: row for row in api.get("/api/signals/current").json()["signals"]}
        assert current["modbus.1001"]["value"] is None
        assert current["modbus.1001"]["error_code"] == "unknown_boiler_state"


def test_added_parameters_are_explicitly_selected_and_read_through_real_loopback(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, COLLECTOR_ENABLED=False, MODBUS_HOST="")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    expected = {"1000": (7, "Rohwert"), "1007": (65, "°C"), "9020": (60, "°C"),
                "9040": (40, "°C"), "1005": (100, "%"), "1012": (0, "Rohwert"), "1013": (20, "min")}
    with TestClient(app) as api, ModbusSimulator() as simulator:
        before = api.get("/api/logging-config").json()
        assert not any(row["code"] in expected for row in before["entries"])
        csv_text = "\n".join(f"Test {code};{int(code, 16)};{code}" for code in expected)
        preview = api.post("/api/logging-config/preview", headers=HEADERS,
                           json={"revision": 0, "csv_text": csv_text}).json()
        assert api.get("/api/logging-config").json()["entries"] == before["entries"]
        for row in preview["entries"]:
            row["record"] = row["code"] in expected
        assert api.put("/api/logging-config", headers=HEADERS,
                       json={"revision": 0, "entries": preview["entries"]}).status_code == 200
        clock = Clock()
        collector = Collector(host=simulator.address[0], port=simulator.address[1],
                              store=app.state.storage, data_dir=tmp_path, max_requests=len(expected),
                              max_duration_seconds=30, retry_on_transport_error=False,
                              monotonic=clock.monotonic, now=clock.now, wait=clock.wait)
        collector.run()
        assert collector.state == "completed"
        current = {row["signal_id"]: row for row in api.get("/api/signals/current").json()["signals"]}
        exported = list(csv.DictReader(io.StringIO(api.get("/api/export.csv").text)))
        for code, (value, unit) in expected.items():
            signal_id = f"modbus.{code}"
            assert (current[signal_id]["value"], current[signal_id]["unit"]) == (value, unit)
            point, = api.get(f"/api/history/{signal_id}").json()["items"]
            assert (point["value"], point["raw_words"], point["quality"]) == (value, [value], "ok")
            row, = [row for row in exported if row["signal_id"] == signal_id]
            assert (row["value"], row["unit"]) == (str(value), unit)
