import sqlite3

from fastapi.testclient import TestClient
import pytest

from backend.config import Settings, get_settings
from backend.main import app
from backend.pellets import pellet_status
from backend.storage import SCHEMA_VERSION, SQLiteStore

HEADERS = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin", "X-Requested-With": "SommerauerMonitor"}


def delivery(hours: float, tonnes: float) -> dict[str, float]:
    return {"operating_hours": hours, "tonnes": tonnes}


def test_erste_lieferung_zaehlt_nicht_zum_verbrauch() -> None:
    result = pellet_status([delivery(1000, 5), delivery(2000, 4), delivery(3000, 6)], 8, 3500)

    assert result == {
        "consumption_kg_per_hour": 5.0,
        "consumed_since_fill_tonnes": 2.5,
        "tank_level_tonnes": 5.5,
    }


@pytest.mark.parametrize(("deliveries", "capacity", "hours", "expected"), [
    ([delivery(1000, 5)], 8, 1500, (None, None, None)),
    ([delivery(1000, 5), delivery(2000, 5)], None, 2100, (5.0, 0.5, None)),
    ([delivery(1000, 5), delivery(2000, 5)], 8, None, (5.0, None, None)),
    ([delivery(1000, 5), delivery(2000, 5)], 8, 1900, (5.0, 0.0, 8.0)),
    ([delivery(1000, 5), delivery(2000, 5)], 1, 3000, (5.0, 5.0, 0.0)),
])
def test_fehlende_grundlagen_und_grenzen(deliveries, capacity, hours, expected) -> None:
    assert tuple(pellet_status(deliveries, capacity, hours).values()) == expected


def test_migration_von_schema_4_erhaelt_datenbank(tmp_path) -> None:
    path = tmp_path / "monitor.sqlite3"
    SQLiteStore(path).save_pellet_capacity(8)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE pellet_deliveries")
        connection.execute("DELETE FROM schema_migrations WHERE version >= 5")
        connection.execute("PRAGMA user_version = 4")

    store = SQLiteStore(path)

    assert store.pellet_data() == {"capacity_tonnes": 8, "deliveries": []}
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_migration_von_schema_5_erhaelt_lieferungen(tmp_path) -> None:
    path = tmp_path / "monitor.sqlite3"
    SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE pellet_deliveries DROP COLUMN supplier")
        connection.execute("ALTER TABLE pellet_deliveries DROP COLUMN price_eur_per_tonne")
        connection.execute(
            "INSERT INTO pellet_deliveries VALUES ('d1', '2026-09-01', 1000, 5, '2026-09-01T00:00:00Z')"
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 6")
        connection.execute("PRAGMA user_version = 5")

    assert SQLiteStore(path).pellet_data()["deliveries"] == [{
        "delivery_id": "d1", "delivered_on": "2026-09-01", "operating_hours": 1000, "tonnes": 5,
        "supplier": None, "price_eur_per_tonne": None,
    }]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.setenv("MODBUS_HOST", "")
    monkeypatch.setenv("PUBLIC_ORIGIN", "")
    monkeypatch.setattr("backend.main.get_settings", lambda: Settings(_env_file=None))
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def record_counter(store: SQLiteStore, minutes: int | None, quality: str = "ok") -> None:
    observed_at = "2026-11-01T10:00:00+00:00"
    store.record_cycle(
        {"request_id": "r1", "started_at": observed_at, "completed_at": observed_at, "function_code": 3,
         "unit_id": 255, "offset": 28688, "register_count": 2, "outcome": "ok", "error_class": None},
        [{"observation_id": "o1", "request_id": "r1", "signal_id": "boiler.operating_minutes",
          "observed_at": observed_at, "value": minutes, "unit": "min", "quality": quality,
          "raw_words": [0, 0], "source": "test", "profile_id": "core", "profile_version": "1",
          "decoder_version": "1"}],
    )


def post(client: TestClient, day: str, hours: float, tonnes: float, **extra):
    return client.post(
        "/api/pellets/deliveries", headers=HEADERS,
        json={"delivered_on": day, "operating_hours": hours, "tonnes": tonnes, **extra},
    )


def test_api_rechnet_mit_gespeichertem_betriebszaehler(client: TestClient) -> None:
    assert post(client, "2025-09-01", 1000, 5).status_code == 201
    assert post(client, "2026-09-01", 2000, 5).status_code == 201
    assert client.put("/api/pellets/tank", headers=HEADERS, json={"capacity_tonnes": 8}).status_code == 200
    record_counter(client.app.state.storage, 2100 * 60)

    body = client.get("/api/pellets").json()

    assert [item["operating_hours"] for item in body["deliveries"]] == [2000, 1000]
    assert body["operating_hours"] == 2100
    assert body["consumed_since_fill_tonnes"] == 0.5
    assert body["tank_level_tonnes"] == 7.5


def test_ungueltiger_zaehler_liefert_keinen_fuellstand(client: TestClient) -> None:
    post(client, "2025-09-01", 1000, 5)
    post(client, "2026-09-01", 2000, 5)
    client.put("/api/pellets/tank", headers=HEADERS, json={"capacity_tonnes": 8})
    record_counter(client.app.state.storage, 2100 * 60, "invalid")

    body = client.get("/api/pellets").json()

    assert body["consumption_kg_per_hour"] == 5
    assert body["tank_level_tonnes"] is None
    assert body["operating_hours_observed_at"] is None


def test_eingaben_werden_geprueft_und_lieferung_ist_loeschbar(client: TestClient) -> None:
    assert post(client, "2026-09-01", 1000, 0).status_code == 422
    assert post(client, "kein-datum", 1000, 5).status_code == 422
    assert post(client, "2026-09-01", -1, 5).status_code == 422
    assert client.put("/api/pellets/tank", headers=HEADERS, json={"capacity_tonnes": 0}).status_code == 422

    created = post(client, "2026-09-01", 1000, 5)
    assert post(client, "2026-09-02", 1000, 5).status_code == 409

    url = f"/api/pellets/deliveries/{created.json()['delivery_id']}"
    assert client.delete(url, headers=HEADERS).status_code == 200
    assert client.delete(url, headers=HEADERS).status_code == 404
    assert client.get("/api/pellets").json()["deliveries"] == []


def test_lieferant_und_preis_sind_optional_und_werden_gespeichert(client: TestClient) -> None:
    assert post(client, "2025-09-01", 1000, 5, supplier="  Pellets Huber ", price_eur_per_tonne=312.5).status_code == 201
    assert post(client, "2026-09-01", 2000, 5, supplier="   ").status_code == 201

    newest, oldest = client.get("/api/pellets").json()["deliveries"]

    assert (oldest["supplier"], oldest["price_eur_per_tonne"]) == ("Pellets Huber", 312.5)
    assert (newest["supplier"], newest["price_eur_per_tonne"]) == (None, None)
    assert post(client, "2026-10-01", 3000, 5, price_eur_per_tonne=0).status_code == 422
    assert post(client, "2026-10-01", 3000, 5, supplier="x" * 101).status_code == 422


def test_lieferung_ist_bearbeitbar_und_verbrauch_rechnet_neu(client: TestClient) -> None:
    post(client, "2025-09-01", 1000, 5)
    second = post(client, "2026-09-01", 2000, 5).json()["delivery_id"]
    url = f"/api/pellets/deliveries/{second}"
    changed = {"delivered_on": "2026-09-02", "operating_hours": 3000, "tonnes": 6,
               "supplier": "Pellets Huber", "price_eur_per_tonne": 320}

    assert client.put(url, headers=HEADERS, json=changed).status_code == 200

    body = client.get("/api/pellets").json()
    assert {key: body["deliveries"][0][key] for key in changed} == changed
    assert body["consumption_kg_per_hour"] == 3

    cleared = {**changed, "supplier": "", "price_eur_per_tonne": None}
    assert client.put(url, headers=HEADERS, json=cleared).status_code == 200
    newest = client.get("/api/pellets").json()["deliveries"][0]
    assert (newest["supplier"], newest["price_eur_per_tonne"]) == (None, None)


def test_bearbeiten_prueft_eingaben_konflikt_und_unbekannte_id(client: TestClient) -> None:
    post(client, "2025-09-01", 1000, 5)
    second = post(client, "2026-09-01", 2000, 5).json()["delivery_id"]
    url = f"/api/pellets/deliveries/{second}"
    valid = {"delivered_on": "2026-09-01", "operating_hours": 2000, "tonnes": 5}

    assert client.put(url, headers=HEADERS, json=valid).status_code == 200
    assert client.put(url, headers=HEADERS, json={**valid, "operating_hours": 1000}).status_code == 409
    assert client.put(url, headers=HEADERS, json={**valid, "tonnes": 0}).status_code == 422
    assert client.put("/api/pellets/deliveries/fehlt", headers=HEADERS, json=valid).status_code == 404
    assert client.put(url, json=valid).status_code == 403
    assert [item["operating_hours"] for item in client.get("/api/pellets").json()["deliveries"]] == [2000, 1000]


def test_mutation_ohne_anwendungskopf_wird_abgewiesen(client: TestClient) -> None:
    response = client.post(
        "/api/pellets/deliveries",
        json={"delivered_on": "2026-09-01", "operating_hours": 1000, "tonnes": 5},
    )
    assert response.status_code == 403
