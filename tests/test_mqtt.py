from datetime import datetime, timedelta, timezone

from backend.config import Settings
from backend.mqtt import MqttPublisher, current_measurements, discovery_components


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
    assert set(retained[1]["components"]) == {"boiler.temperature"}
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
    assert messages[-1] == ("homeassistant/device/test-monitor/config", None, retained[2])
