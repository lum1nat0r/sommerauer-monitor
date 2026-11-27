from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.mqtt import PELLET_SENSORS, MqttPublisher, current_measurements, discovery_components
from backend.pellets import OPERATING_COUNTER_SIGNAL
from backend.storage import SQLiteStore, StorageError


def test_only_fresh_committed_measurements_of_the_current_run_are_sent():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start = now - timedelta(hours=1)
    signal = "boiler.temperature"
    row = {"signal_id": signal, "value": 0, "quality": "ok", "observed_at": now.isoformat(), "unit": "°C"}
    assert current_measurements([row], {signal}, start, now) == {
        signal: {"value": 0, "observed_at": now.isoformat()},
    }
    assert current_measurements([row], set(), start, now) == {}
    assert current_measurements([row], {signal}, now + timedelta(seconds=1), now) == {}
    for change in (
        {"quality": "invalid"}, {"quality": "unavailable"}, {"value": None}, {"value": float("inf")},
        {"observed_at": (now - timedelta(seconds=241)).isoformat()},
        {"observed_at": (now + timedelta(seconds=1)).isoformat()}, {"unit": "V"},
    ):
        assert current_measurements([{**row, **change}], {signal}, start, now) == {}


def test_discovery_preserves_ids_and_marks_only_documented_statistics():
    selected = {"boiler.temperature", "boiler.operating_minutes", "stoker.operating_minutes", "modbus.1007", "modbus.95E0"}
    components = discovery_components("test-monitor", selected)
    assert set(components) == selected
    assert components["boiler.temperature"]["unique_id"] == "test-monitor_boiler.temperature"
    assert components["boiler.temperature"]["state_class"] == "measurement"
    assert components["boiler.operating_minutes"]["state_class"] == "total_increasing"
    assert "state_class" not in components["stoker.operating_minutes"]
    assert "state_class" not in components["modbus.1007"]
    assert "unit_of_measurement" not in components["modbus.95E0"]
    assert all(component["expire_after"] == 45 for component in components.values())


@pytest.fixture
def pellet_publisher(tmp_path, monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    settings = Settings(_env_file=None, DATA_DIR=tmp_path, MQTT_INSTANCE_ID="test-monitor")
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    collector = SimpleNamespace(status=lambda: {"state": "running"})
    publisher = MqttPublisher(settings, store, collector, now - timedelta(hours=1))
    row = {"signal_id": OPERATING_COUNTER_SIGNAL, "value": 2100 * 60, "quality": "ok",
           "observed_at": now.isoformat(), "unit": "min"}
    monkeypatch.setattr(store, "current_signals", lambda: [row])
    return publisher, row, now


def test_pellet_estimates_use_saved_deliveries_and_counter(pellet_publisher):
    publisher, row, now = pellet_publisher
    eligible = {OPERATING_COUNTER_SIGNAL}
    store = publisher.storage
    store.add_pellet_delivery("a", "2025-09-01", 1000, 5)
    assert set(publisher._measurements(eligible, now)) == eligible
    store.add_pellet_delivery("b", "2025-12-01", 2000, 5, "Testlieferant", 350)
    assert set(publisher._measurements(eligible, now)) == eligible | {
        "pellets.consumed_since_fill_tonnes",
    }
    store.save_pellet_capacity(8)

    def expected(level, percent, consumed):
        return {
            signal_id: {"value": value, "observed_at": now.isoformat()}
            for signal_id, value in {
                "pellets.tank_level_tonnes": level,
                "pellets.tank_level_percent": percent,
                "pellets.consumed_since_fill_tonnes": consumed,
                OPERATING_COUNTER_SIGNAL: row["value"],
            }.items()
        }

    assert publisher._measurements(eligible, now) == expected(7.5, 93.75, 0.5)
    store.update_pellet_delivery("b", "2025-12-01", 2000, 10, None, None)
    assert publisher._measurements(eligible, now) == expected(7, 87.5, 1)
    row["value"] = 2000 * 60
    assert publisher._measurements(eligible, now) == expected(8, 100, 0)
    row["value"] = 3000 * 60
    assert publisher._measurements(eligible, now) == expected(0, 0, 10)
    store.update_pellet_delivery("b", "2025-12-01", 2000, 1e308, None, None)
    assert set(publisher._measurements(eligible, now)) == eligible


def test_pellet_estimates_require_an_eligible_counter(pellet_publisher):
    publisher, row, now = pellet_publisher
    eligible = {OPERATING_COUNTER_SIGNAL}
    assert publisher._measurements(set(), now) == {}
    assert publisher._measurements(eligible, now + timedelta(seconds=241)) == {}
    publisher.started_at = now + timedelta(seconds=1)
    assert publisher._measurements(eligible, now + timedelta(seconds=1)) == {}
    publisher.started_at = now
    row["quality"] = "invalid"
    assert publisher._measurements(eligible, now) == {}
    row["quality"] = "ok"
    publisher.collector.status = lambda: {"state": "paused"}
    assert publisher._measurements(eligible, now) == {}


def test_pellet_storage_errors_preserve_register_telemetry(pellet_publisher, monkeypatch):
    publisher, row, now = pellet_publisher

    def unavailable():
        raise StorageError("Pelletdaten nicht verfügbar")

    monkeypatch.setattr(publisher.storage, "pellet_data", unavailable)
    assert publisher._measurements({OPERATING_COUNTER_SIGNAL}, now) == {
        OPERATING_COUNTER_SIGNAL: {"value": row["value"], "observed_at": now.isoformat()},
    }


def test_discovery_explicitly_removes_inactive_signals_then_retains_active_configuration(
    tmp_path, monkeypatch,
):
    import json

    settings = Settings(_env_file=None, DATA_DIR=tmp_path, MQTT_INSTANCE_ID="test-monitor")
    publisher = MqttPublisher(settings, None, None, datetime.now(timezone.utc))
    messages = []

    def record(topic, payload, **options):
        messages.append((topic, json.loads(payload) if payload else None, options))

    active = {"boiler.temperature", "boiler.operating_minutes"}
    publisher._reconcile_discovery(record, lambda _: None, active, False)
    assert len(messages) == 1
    publisher._reconcile_discovery(record, lambda _: None, {"boiler.temperature"}, False)
    deleted, retained = messages[1:]
    assert deleted[1]["components"] == {"boiler.operating_minutes": {"platform": "sensor"}}
    assert deleted[2] == {"reliable": True}
    assert set(retained[1]["components"]) == {"boiler.temperature"} | PELLET_SENSORS.keys()
    assert retained[2] == {"reliable": True, "retain": True}
    assert json.loads(publisher.discovery_file.read_text()) == [
        ["boiler.temperature"], ["boiler.operating_minutes"],
    ]
    clock = iter([0, 2])
    monkeypatch.setattr("backend.mqtt.monotonic", lambda: next(clock))
    publisher._reconcile_discovery(record, lambda _: None, {"boiler.temperature"}, True)
    reloaded, deleted, retained = messages[-3:]
    assert reloaded[1]["components"]["boiler.operating_minutes"]["unique_id"] == (
        "test-monitor_boiler.operating_minutes"
    )
    assert deleted[1]["components"] == {"boiler.operating_minutes": {"platform": "sensor"}}
    assert json.loads(publisher.discovery_file.read_text()) == [["boiler.temperature"], []]
    publisher._reconcile_discovery(record, lambda _: None, set(), False)
    topic, discovery, options = messages[-1]
    assert topic == "homeassistant/device/test-monitor/config"
    assert options == retained[2]
    assert set(discovery["components"]) == {
        "pellets.tank_level_tonnes", "pellets.tank_level_percent", "pellets.consumed_since_fill_tonnes",
    }
    for signal_id, component in discovery["components"].items():
        assert component["unique_id"] == f"test-monitor_{signal_id}"
        assert component["unit_of_measurement"] == ("%" if signal_id.endswith("_percent") else "t")
        assert "device_class" not in component
        assert component["expire_after"] == 45
    assert "state_class" not in discovery["components"]["pellets.consumed_since_fill_tonnes"]
