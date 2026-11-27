"""Read-only Home Assistant telemetry from committed observations and pellet estimates."""

from datetime import datetime, timezone
import json
import logging
import math
import ssl
from threading import Event, Thread
from time import monotonic

from paho.mqtt import client as mqtt

from backend.collector import Collector
from backend.config import Settings
from backend.pellets import OPERATING_COUNTER_SIGNAL, pellet_status
from backend.registers import SIGNAL_DEFINITIONS, signal_freshness_seconds
from backend.storage import SQLiteStore, StorageError


LOGGER = logging.getLogger(__name__)
PUBLISH_SECONDS = 15
IO_TIMEOUT = 3
HA_BIRTH_TOPIC = "homeassistant/status"
COLLECTING = {"running", "retry_wait", "reconnect_wait"}
PELLET_SENSORS = {
    "pellets.tank_level_tonnes": ("Geschätzter Pellet-Tankfüllstand", "t"),
    "pellets.tank_level_percent": ("Geschätzter Pellet-Tankfüllstand in Prozent", "%"),
    "pellets.consumed_since_fill_tonnes": ("Geschätzter Pelletverbrauch seit Befüllung", "t"),
}


def discovery_components(instance: str, active: set[str]) -> dict[str, dict]:
    components = {}
    for signal_id in sorted(active):
        if signal_id in PELLET_SENSORS:
            label, unit = PELLET_SENSORS[signal_id]
            kind = "estimate"
        else:
            definition = SIGNAL_DEFINITIONS[signal_id]
            label, unit, kind = definition["label"], definition["unit"], definition["kind"]
        key = json.dumps(signal_id)
        item = f"value_json.get({key})"
        component = {
            "platform": "sensor",
            "unique_id": f"{instance}_{signal_id}",
            "name": label,
            "state_topic": f"{instance}/state",
            "value_template": "{{ (" + item + " or {}).get('value') }}",
            "json_attributes_topic": f"{instance}/state",
            "json_attributes_template": (
                "{{ {'observed_at': " + item + ".observed_at} | tojson if "
                + item + " else '{}' }}"
            ),
            "availability": [
                {"topic": f"{instance}/availability"},
                {
                    "topic": f"{instance}/state",
                    "value_template": "{{ 'online' if " + item + " else 'offline' }}",
                },
            ],
            "availability_mode": "all",
            "expire_after": 3 * PUBLISH_SECONDS,
        }
        if unit and unit != "Rohwert":
            component["unit_of_measurement"] = unit
        if unit == "°C":
            component["device_class"] = "temperature"
        elif unit == "V":
            component["device_class"] = "voltage"
        elif signal_id in {"boiler.operating_minutes", "stoker.operating_minutes"}:
            component["device_class"] = "duration"
        if (kind == "measurement" and unit in {"°C", "V"}) or signal_id in {
            "pellets.tank_level_tonnes", "pellets.tank_level_percent",
        }:
            component["state_class"] = "measurement"
        if signal_id == "boiler.operating_minutes":
            component["state_class"] = "total_increasing"
        components[signal_id] = component
    return components


def current_measurements(
    rows: list[dict], eligible: set[str], since: datetime, now: datetime,
) -> dict[str, dict]:
    result = {}
    for row in rows:
        signal_id = row["signal_id"]
        value = row["value"]
        if signal_id not in eligible or row["quality"] != "ok" or value is None:
            continue
        observed = datetime.fromisoformat(row["observed_at"])
        if (
            not since <= observed <= now
            or (now - observed).total_seconds() > signal_freshness_seconds(signal_id)
            or not math.isfinite(value)
            or row["unit"] != SIGNAL_DEFINITIONS[signal_id]["unit"]
        ):
            continue
        result[signal_id] = {"value": value, "observed_at": row["observed_at"]}
    return result


class MqttPublisher:
    def __init__(
        self, settings: Settings, storage: SQLiteStore, collector: Collector, started_at: datetime,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.collector = collector
        self.started_at = started_at
        self.instance = settings.mqtt_instance_id
        self.discovery_file = settings.data_dir / f"mqtt-{self.instance}.json"
        self.discovery_topic = f"homeassistant/device/{self.instance}/config"
        self.availability_topic = f"{self.instance}/availability"
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="mqtt-telemetry", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self) -> None:
        delay = 1
        while not self.stop_event.is_set():
            session_started = monotonic()
            try:
                self._session()
            except (OSError, ValueError, StorageError) as exc:
                LOGGER.warning("MQTT-Telemetrie unterbrochen (%s).", type(exc).__name__)
            if monotonic() - session_started >= PUBLISH_SECONDS:
                delay = 1
            if self.stop_event.wait(delay):
                return
            delay = min(delay * 2, 60)

    def _session(self) -> None:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self.instance,
            protocol=mqtt.MQTTv5,
        )
        client.connect_timeout = IO_TIMEOUT
        tls_dir = self.settings.mqtt_tls_dir
        context = ssl.create_default_context(cafile=str(tls_dir / "ca.crt"))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(tls_dir / "client.crt", tls_dir / "client.key")
        client.tls_set_context(context)
        client.will_set(self.availability_topic, "offline", qos=1)
        connected = subscribed = refresh = False
        pending_mid = None
        acknowledged = None
        last_active = None
        next_publish = 0.0

        def on_connect(client, _userdata, _flags, reason, _properties):
            nonlocal connected
            connected = not reason.is_failure
            if connected:
                client.subscribe(HA_BIRTH_TOPIC, qos=1)

        def on_subscribe(_client, _userdata, _mid, reasons, _properties):
            nonlocal subscribed
            subscribed = bool(reasons) and not any(reason.is_failure for reason in reasons)

        def on_message(_client, _userdata, message):
            nonlocal refresh
            if message.topic == HA_BIRTH_TOPIC and message.payload == b"online":
                refresh = True

        def on_publish(_client, _userdata, mid, reason, _properties):
            nonlocal acknowledged
            if mid == pending_mid:
                acknowledged = not reason.is_failure

        def pump(timeout: float) -> None:
            if client.loop(timeout=timeout) != mqtt.MQTT_ERR_SUCCESS:
                raise ConnectionError("MQTT connection lost")

        def publish(topic: str, payload: str, *, reliable: bool = False, retain: bool = False) -> None:
            nonlocal pending_mid, acknowledged
            info = client.publish(topic, payload, qos=int(reliable), retain=retain)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise ConnectionError("MQTT publish failed")
            if reliable:
                pending_mid = info.mid
                acknowledged = None
                deadline = monotonic() + IO_TIMEOUT
                while acknowledged is None and monotonic() < deadline:
                    pump(0.2)
                pending_mid = None
                if not acknowledged:
                    raise ConnectionError("MQTT publish was not acknowledged")

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_publish = on_publish
        try:
            client.connect(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=15)
            deadline = monotonic() + IO_TIMEOUT
            while not subscribed and monotonic() < deadline and not self.stop_event.is_set():
                pump(0.2)
            if not subscribed:
                raise ConnectionError("MQTT subscription was not acknowledged")
            LOGGER.info("MQTT-Telemetrie verbunden.")
            while not self.stop_event.is_set():
                if refresh or monotonic() >= next_publish:
                    force_discovery, refresh = refresh, False
                    active, suspended = self.collector.telemetry_signals()
                    if force_discovery or active != last_active:
                        self._reconcile_discovery(publish, pump, active, force_discovery)
                        last_active = active
                    measurements = self._measurements(active - suspended, datetime.now(timezone.utc))
                    publish(f"{self.instance}/state", json.dumps(measurements))
                    publish(self.availability_topic, "online")
                    next_publish = monotonic() + PUBLISH_SECONDS
                pump(0.5)
        finally:
            if client.is_connected():
                # A failed offline publish must leave the broker's Will armed.
                publish(self.availability_topic, "offline", reliable=True)
                client.disconnect()

    def _measurements(self, eligible: set[str], now: datetime) -> dict[str, dict]:
        if self.collector.status()["state"] not in COLLECTING:
            return {}
        measurements = current_measurements(
            self.storage.current_signals(), eligible, self.started_at, now,
        )
        counter = measurements.get(OPERATING_COUNTER_SIGNAL)
        if counter is None:
            return measurements
        try:
            data = self.storage.pellet_data()
        except StorageError:
            LOGGER.warning("Pelletschätzungen für MQTT nicht verfügbar.")
            return measurements
        capacity = data["capacity_tonnes"]
        status = pellet_status(data["deliveries"], capacity, counter["value"] / 60)
        consumed = status["consumed_since_fill_tonnes"]
        if consumed is None or not math.isfinite(consumed):
            return measurements
        level = status["tank_level_tonnes"]
        estimates = {
            "pellets.tank_level_tonnes": level,
            "pellets.tank_level_percent": level / capacity * 100 if level is not None else None,
            "pellets.consumed_since_fill_tonnes": consumed,
        }
        for signal_id, value in estimates.items():
            if value is not None:
                measurements[signal_id] = {"value": value, "observed_at": counter["observed_at"]}
        return measurements

    def _discovery_payload(self, components: dict[str, dict]) -> str:
        return json.dumps({
            "device": {"identifiers": [self.instance], "name": "Sommerauer Monitor"},
            "origin": {"name": "Sommerauer Monitor"},
            "components": components,
        })

    def _save_discovery(self, active: set[str], pending: set[str]) -> None:
        temporary = self.discovery_file.with_suffix(".tmp")
        temporary.write_text(json.dumps([sorted(active), sorted(pending)]), encoding="utf-8")
        temporary.replace(self.discovery_file)

    def _reconcile_discovery(self, publish, pump, active: set[str], ha_started: bool) -> None:
        try:
            previous, pending = json.loads(self.discovery_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            previous, pending = [], []
        if not all(
            isinstance(ids, list) and all(isinstance(signal_id, str) for signal_id in ids)
            for ids in (previous, pending)
        ):
            raise ValueError("Invalid MQTT discovery journal")
        removed = ((set(previous) | set(pending)) - active) & SIGNAL_DEFINITIONS.keys()
        if set(previous) != active or set(pending) != removed:
            self._save_discovery(active, removed)
        if removed:
            if ha_started:
                # shortcut: HA has no discovery ACK; allow it to load old IDs before deletion.
                old_components = discovery_components(self.instance, removed)
                publish(self.discovery_topic, self._discovery_payload(old_components), reliable=True)
                deadline = monotonic() + 2
                while monotonic() < deadline and not self.stop_event.is_set():
                    pump(0.2)
            tombstones = {signal_id: {"platform": "sensor"} for signal_id in sorted(removed)}
            publish(self.discovery_topic, self._discovery_payload(tombstones), reliable=True)
        components = discovery_components(self.instance, active | PELLET_SENSORS.keys())
        publish(self.discovery_topic, self._discovery_payload(components), reliable=True, retain=True)
        if removed and ha_started:
            self._save_discovery(active, set())
