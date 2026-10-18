from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from datetime import timedelta
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from backend.collector import Collector
from backend.config import Settings, get_settings
from backend.logging_config import (
    MAX_CSV_BYTES, MAX_ENTRIES, MAX_REQUEST_BYTES, LoggingConfigError,
    default_entries, merge_csv, normalize_entries, parse_csv, selected_signal_ids,
)
from backend.main import app
from backend.storage import LoggingConfigConflict, SQLiteStore, StorageError


MUTATION_HEADERS = {
    "Origin": "http://testserver",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "SommerauerMonitor",
}


def indexed(entries):
    return {entry["code"]: entry for entry in entries}


@pytest.fixture
def offline_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COLLECTOR_ENABLED", "false")
    monkeypatch.setenv("MODBUS_HOST", "")
    monkeypatch.setenv("MODBUS_PORT", "1502")
    monkeypatch.setenv("MODBUS_UNIT_ID", "255")
    monkeypatch.setenv("COLLECTOR_MAX_REQUESTS", "")
    monkeypatch.setenv("REGISTER_PROFILE", "core")
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Europe/Vienna")
    monkeypatch.setenv("PUBLIC_ORIGIN", "")
    monkeypatch.setattr("backend.main.get_settings", lambda: Settings(_env_file=None))

    def forbidden_device_access(*args, **kwargs):
        pytest.fail("Konfigurationsendpunkte dürfen keinen Modbus-Client erzeugen")

    monkeypatch.setattr("backend.collector.ModbusTcpClient", forbidden_device_access)
    get_settings.cache_clear()
    yield app
    get_settings.cache_clear()


def test_default_snapshot_preserves_confirmed_core_selection_without_writing(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    snapshot = store.get_logging_config()
    entries = indexed(snapshot["entries"])

    assert snapshot["revision"] == 0
    assert set(entries) == {"1006", "7010", "7011", "9000", "9001"}
    assert all(entry["eligible"] and entry["record"] for entry in entries.values())
    assert selected_signal_ids(snapshot["entries"]) == {
        "boiler.temperature", "boiler.operating_minutes",
        "buffer.top_temperature", "buffer.bottom_temperature",
    }
    assert entries["7010"]["signal_id"] == entries["7011"]["signal_id"] == "boiler.operating_minutes"
    snapshot["entries"][0]["name"] = "Nur lokale Kopie"
    snapshot["entries"][0]["changed_fields"].append("name")
    assert store.get_logging_config()["entries"] == default_entries()
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM logging_config").fetchone()[0] == 0


def test_incremental_merge_preserves_missing_rows_and_operator_texts():
    original = default_entries()
    indexed(original)["1006"].update(unit="Betreibereinheit", description="Eigener Hinweis")
    draft = merge_csv(original, "Kessel_neu;4102;1006\nNoch_unbestätigt;99;abcd\n")
    entries = indexed(draft)

    assert len(entries) == 6
    assert entries["1006"]["name"] == "Kessel_neu"
    assert entries["1006"]["record"] is True
    assert entries["1006"]["unit"] == "Betreibereinheit"
    assert entries["1006"]["description"] == "Eigener Hinweis"
    assert entries["1006"]["change"] == "changed"
    assert entries["1006"]["changed_fields"] == ["name"]
    assert entries["ABCD"]["change"] == "new"
    assert entries["ABCD"]["offset"] == 99
    assert entries["ABCD"]["record"] is False
    assert entries["ABCD"]["eligible"] is False
    assert entries["ABCD"]["signal_id"] is None
    assert entries["9000"] == indexed(original)["9000"]
    assert indexed(original)["1006"]["name"] != "Kessel_neu"


def test_csv_reorder_is_idempotent_and_supports_bom_crlf_and_quoted_names():
    original = default_entries()
    rows = [f'"{entry["name"]}";{entry["offset"]};{entry["code"]}' for entry in original]
    csv_text = "\ufeff" + "\r\n".join(reversed(rows)) + "\r\n\r\n"

    assert merge_csv(original, csv_text) == original
    assert parse_csv('"Name;mit Semikolon";123;abcd')[0] == {
        "code": "ABCD", "offset": 123, "name": "Name;mit Semikolon",
    }
    assert parse_csv("Nullen;" + "0" * 5000 + "123;ABCD")[0]["offset"] == 123


def test_offset_change_disables_recording_and_blocks_core_decoder():
    draft = indexed(merge_csv(default_entries(), "Kessel_Ist;4103;1006"))
    assert draft["1006"]["record"] is False
    assert draft["1006"]["eligible"] is False
    assert "4102" in draft["1006"]["blocked_reason"]
    assert draft["1006"]["changed_fields"] == ["offset"]
    assert draft["9000"]["record"] is True


def test_counter_word_change_disables_both_words_and_requires_complete_mapping():
    draft = indexed(merge_csv(default_entries(), "Betrieb_Min;30000;7011"))
    assert all(not draft[code]["record"] and not draft[code]["eligible"] for code in ("7010", "7011"))
    assert draft["7010"]["changed_fields"] == []
    assert draft["7010"]["change"] == "unchanged"
    assert "gemeinsam" in draft["7010"]["blocked_reason"]
    partial = [deepcopy(indexed(default_entries())["7010"])]
    partial[0]["record"] = False
    assert normalize_entries(partial)[0]["eligible"] is False
    restored = indexed(merge_csv(list(draft.values()), "Betrieb_Min;28689;7011"))
    assert all(restored[code]["eligible"] and restored[code]["record"] for code in ("7010", "7011"))


@pytest.mark.parametrize(("csv_text", "message"), [
    ("", "keine Registerzeilen"),
    ("Name;Offset;Code", "Hexzeichen"),
    ("Name;1;ABCD;zu viel", "Erwartet wird"),
    ("Name;-1;ABCD", "dezimal"),
    ("Name;0x10;ABCD", "dezimal"),
    ("Name;65536;ABCD", "65535"),
    ("Name;" + "9" * 5000 + ";ABCD", "65535"),
    ("Name;1;XYZ1", "Hexzeichen"),
    (";1;ABCD", "Name"),
    ('"offen;1;ABCD', "CSV-Syntax"),
    ("Name;1;ABCD\nName;1;abcd", "Identischer doppelter"),
    ("Name;1;ABCD\nAnderer Name;2;ABCD", "Widersprüchlicher doppelter"),
    ("Name;1;ABCD\nAnderer Name;1;ABCE", "Offset 1 ist mehrfach"),
])
def test_invalid_csv_is_rejected_without_mutating_entries(csv_text, message):
    original = default_entries()
    before = deepcopy(original)
    with pytest.raises(LoggingConfigError, match=message):
        merge_csv(original, csv_text)
    assert original == before


def test_csv_and_entry_limits_are_bounded():
    with pytest.raises(LoggingConfigError, match="1 MiB"):
        parse_csv("x" * (MAX_CSV_BYTES + 1))
    with pytest.raises(LoggingConfigError, match=str(MAX_ENTRIES)):
        normalize_entries([{}] * (MAX_ENTRIES + 1))
    with pytest.raises(LoggingConfigError, match="Unicode"):
        parse_csv("Name;1;ABCD\ud800")


@pytest.mark.parametrize("mutation", [
    lambda entries: entries[0].update(record="true"),
    lambda entries: entries[0].update(offset=True),
    lambda entries: entries[0].update(offset=65536),
    lambda entries: entries[0].update(name=""),
    lambda entries: entries[0].update(offset=indexed(entries)["9000"]["offset"], record=False),
    lambda entries: entries[0].update(unit="x" * 41),
    lambda entries: entries[0].update(description="x" * 2001),
    lambda entries: entries[0].update(signal_id="invented.signal"),
    lambda entries: entries[0].update(extra="nicht erlaubt"),
    lambda entries: entries.append(deepcopy(entries[0])),
    lambda entries: entries.pop(),
    lambda entries: indexed(entries)["7010"].update(record=False),
])
def test_store_rejects_manipulated_entries_atomically(tmp_path, mutation):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    before = store.get_logging_config()
    changed = deepcopy(before["entries"])
    mutation(changed)
    with pytest.raises(LoggingConfigError):
        store.save_logging_config(before["revision"], changed)
    assert store.get_logging_config() == before


def test_unsupported_and_reassigned_offsets_cannot_bypass_freigabe(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    draft = merge_csv(default_entries(), "Unbekannt;4102;ABCD\nFalsch;99;1006")
    indexed(draft)["ABCD"].update(record=True, eligible=True, blocked_reason=None)
    with pytest.raises(LoggingConfigError):
        store.save_logging_config(0, draft)
    indexed(draft)["ABCD"]["record"] = False
    indexed(draft)["1006"].update(record=True, eligible=True, blocked_reason=None)
    with pytest.raises(LoggingConfigError):
        store.save_logging_config(0, draft)
    assert store.get_logging_config()["revision"] == 0


def test_save_restart_reimport_preserve_metadata_and_clear_draft_markers(tmp_path):
    path = tmp_path / "monitor.sqlite3"
    store = SQLiteStore(path)
    draft = merge_csv(default_entries(), "Neu;4102;1006\nKandidat;17;ABCD")
    indexed(draft)["1006"].update(record=False, unit="keine Umrechnung", description="Hinweis vom Betreiber")
    saved = store.save_logging_config(0, draft)
    restarted = SQLiteStore(path)

    assert saved["revision"] == 1
    assert restarted.get_logging_config() == saved
    assert all(entry["change"] == "unchanged" and entry["changed_fields"] == [] for entry in saved["entries"])
    reimported = merge_csv(saved["entries"], "Anderer Name;4102;1006")
    entry = indexed(reimported)["1006"]
    assert (entry["unit"], entry["description"], entry["record"]) == (
        "keine Umrechnung", "Hinweis vom Betreiber", True,
    )
    saved["entries"][0]["description"] = "Nur Antwortkopie"
    assert restarted.get_logging_config() != saved


def test_atomic_cas_has_one_winner_and_stale_revision_changes_nothing(tmp_path):
    path = tmp_path / "monitor.sqlite3"
    first = SQLiteStore(path)
    second = SQLiteStore(path)
    barrier = Barrier(2)

    def save(store, description):
        entries = default_entries()
        entries[0]["description"] = description
        barrier.wait(timeout=5)
        try:
            return store.save_logging_config(0, entries)
        except LoggingConfigConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save, first, "A"), pool.submit(save, second, "B")]
        results = [future.result(timeout=10) for future in futures]
    winners = [result for result in results if isinstance(result, dict)]
    assert len(winners) == 1
    assert sum(isinstance(result, LoggingConfigConflict) for result in results) == 1
    assert first.get_logging_config() == winners[0]
    with pytest.raises(LoggingConfigConflict):
        second.save_logging_config(0, default_entries())
    assert first.get_logging_config() == winners[0]


def test_identical_reordered_reimport_and_save_are_true_noops(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    original = store.get_logging_config()
    assert store.save_logging_config(0, list(reversed(original["entries"]))) == original
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM logging_config").fetchone()[0] == 0
    changed = deepcopy(original["entries"])
    changed[0]["description"] = "Betreibertext"
    saved = store.save_logging_config(0, changed)
    with sqlite3.connect(store.path) as connection:
        connection.execute("""CREATE TRIGGER forbid_noop_update BEFORE UPDATE ON logging_config
                           BEGIN SELECT RAISE(ABORT, 'unexpected update'); END""")
    csv_text = "\n".join(
        f"{entry['name']};{entry['offset']};{entry['code']}"
        for entry in reversed(saved["entries"])
    )
    draft = merge_csv(saved["entries"], csv_text)
    assert draft == saved["entries"]
    assert store.save_logging_config(saved["revision"], list(reversed(draft))) == saved
    assert store.get_logging_config() == saved


def test_reimport_cannot_reuse_offset_of_preserved_entry(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    before = store.get_logging_config()
    with pytest.raises(LoggingConfigError, match="Offset 4102 ist mehrfach"):
        merge_csv(before["entries"], "Anderer Code;4102;ABCD")
    assert store.get_logging_config() == before


def test_corrected_core_mapping_is_preselected_only_in_draft_until_saved(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    wrong = merge_csv(default_entries(), "Kessel_Ist;4103;1006")
    saved = store.save_logging_config(0, wrong)
    corrected = merge_csv(saved["entries"], "Kessel_Ist;4102;1006")
    assert indexed(corrected)["1006"]["eligible"] is True
    assert indexed(corrected)["1006"]["record"] is True
    assert store.get_logging_config() == saved
    accepted = store.save_logging_config(saved["revision"], corrected)
    assert indexed(accepted["entries"])["1006"]["record"] is True


def test_database_write_failure_preserves_last_revision(tmp_path):
    store = SQLiteStore(tmp_path / "monitor.sqlite3")
    initial = default_entries()
    initial[0]["description"] = "Gespeicherter Bestand"
    saved = store.save_logging_config(0, initial)
    with sqlite3.connect(store.path) as connection:
        connection.execute("""CREATE TRIGGER fail_logging_update BEFORE UPDATE ON logging_config
                           BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    changed = deepcopy(saved["entries"])
    changed[0]["record"] = False
    with pytest.raises(StorageError):
        store.save_logging_config(saved["revision"], changed)
    assert store.get_logging_config() == saved


def test_preview_save_and_restart_are_offline_and_preview_has_no_writes(offline_app):
    with TestClient(offline_app) as client:
        before = client.get("/api/logging-config").json()
        preview = client.post("/api/logging-config/preview", headers=MUTATION_HEADERS, json={
            "revision": before["revision"], "csv_text": "Importname;4102;1006\nKandidat;17;ABCD",
        })
        assert preview.status_code == 200
        draft = preview.json()
        assert draft["revision"] == before["revision"]
        assert draft["active_entries"] == before["entries"]
        assert draft["active_revision"] == before["revision"]
        assert draft["apply_status"] == "inaktiv"
        assert client.get("/api/logging-config").json() == before
        saved_response = client.put("/api/logging-config", headers=MUTATION_HEADERS, json={
            "revision": draft["revision"], "entries": draft["entries"],
        })
        assert saved_response.status_code == 200
        saved = saved_response.json()
        assert saved["revision"] == 1
        assert saved["active_entries"] == saved["entries"]
        assert saved["active_revision"] == 1
        assert all(entry["change"] == "unchanged" for entry in saved["entries"])
    with TestClient(offline_app) as client:
        assert client.get("/api/logging-config").json() == saved


@pytest.mark.parametrize("state", ["paused", "stopped_protocol", "stopped_data", "stopped_transport", "reconnect_wait", "completed"])
def test_saved_selection_is_pending_and_failed_save_keeps_active_snapshot(offline_app, monkeypatch, tmp_path, state):
    with TestClient(offline_app) as client:
        before = client.get("/api/logging-config").json()
        collector = Collector(
            host="unused.invalid", port=502, store=offline_app.state.storage,
            data_dir=tmp_path, client=object(),
        )
        collector.state = state
        collector._reconnect_attempts = 2
        collector._retry_delay_seconds = 120
        collector._retry_at = collector.now() + timedelta(seconds=120)
        collector._retry_monotonic_deadline = collector.monotonic() + 120
        collector._persist_state()
        offline_app.state.collector = collector
        saved_state = offline_app.state.storage.get_collector_state()
        entries = deepcopy(before["entries"])
        entries[0]["record"] = False
        response = client.put("/api/logging-config", headers=MUTATION_HEADERS, json={
            "revision": before["revision"], "entries": entries,
        })
        assert response.status_code == 200
        saved = response.json()
        assert saved["apply_status"] == "ausstehend"
        assert saved["active_entries"] == before["entries"]
        assert saved["active_revision"] == before["revision"]
        assert collector.state == state
        assert collector.status()["reconnect_attempts"] == 2
        assert offline_app.state.storage.get_collector_state() == saved_state
        stale = client.put("/api/logging-config", headers=MUTATION_HEADERS, json={
            "revision": before["revision"], "entries": entries,
        })
        assert stale.status_code == 409
        assert client.get("/api/logging-config").json() == saved

        def fail_save(*args):
            raise StorageError("private database path")

        monkeypatch.setattr(offline_app.state.storage, "save_logging_config", fail_save)
        failure = client.put("/api/logging-config", headers=MUTATION_HEADERS, json={
            "revision": saved["revision"], "entries": entries,
        })
        assert failure.status_code == 503
        assert "private database path" not in failure.text
        assert client.get("/api/logging-config").json() == saved
        assert collector.state == state
        assert collector._thread is None
        assert offline_app.state.storage.get_collector_state() == saved_state


def test_preview_conflicts_and_mutations_use_same_origin_guard(offline_app):
    with TestClient(offline_app) as client:
        snapshot = client.get("/api/logging-config").json()
        for route, body in (
            ("/api/logging-config/preview", {"revision": 0, "csv_text": "Name;4102;1006"}),
            ("/api/logging-config", {"revision": 0, "entries": snapshot["entries"]}),
        ):
            method = client.post if route.endswith("preview") else client.put
            assert method(route, json=body).status_code == 403
            assert method(route, json=body, headers={**MUTATION_HEADERS, "Origin": "https://fremd.invalid"}).status_code == 403
        conflict = client.post("/api/logging-config/preview", headers=MUTATION_HEADERS, json={
            "revision": 99, "csv_text": "Name;4102;1006",
        })
        assert conflict.status_code == 409
        assert client.get("/api/logging-config").json() == snapshot


@pytest.mark.parametrize("payload", [
    {}, {"revision": True, "csv_text": "Name;1;ABCD"},
    {"revision": -1, "csv_text": "Name;1;ABCD"},
    {"revision": "0", "csv_text": "Name;1;ABCD"},
    {"revision": 0, "csv_text": 42},
    {"revision": 0, "csv_text": "Name;1;ABCD", "extra": True},
])
def test_api_rejects_invalid_payloads_with_german_detail(offline_app, payload):
    with TestClient(offline_app) as client:
        response = client.post("/api/logging-config/preview", headers=MUTATION_HEADERS, json=payload)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)
        assert client.get("/api/logging-config").json()["revision"] == 0


def test_api_limits_json_and_csv_before_saving(offline_app):
    with TestClient(offline_app) as client:
        huge_body = client.put("/api/logging-config", headers=MUTATION_HEADERS,
                               content=b" " * (MAX_REQUEST_BYTES + 1))
        assert huge_body.status_code == 413
        huge_csv = client.post("/api/logging-config/preview", headers=MUTATION_HEADERS, json={
            "revision": 0, "csv_text": "x" * (MAX_CSV_BYTES + 1),
        })
        assert huge_csv.status_code == 422
        malformed = client.put("/api/logging-config", headers=MUTATION_HEADERS, content=b"{not-json")
        assert malformed.status_code == 422
        assert client.get("/api/logging-config").json()["revision"] == 0


def test_csv_preselects_only_interpretable_mappings_and_complete_counter_pairs():
    draft = indexed(merge_csv(default_entries(),
        "Leistung;4099;1003\nLambda;4356;1104\nProtokoll;4848;12F0\n"
        "Unbekannt;99;ABCD\nSTART;36928;9040\nStoker_Tag;28690;7012\n"
        "Falsche_Zuordnung;4103;1006"))
    for code in ("1003", "1104", "12F0"):
        assert draft[code]["eligible"] is True
        assert draft[code]["record"] is True
    for code in ("ABCD", "9040", "7012", "1006"):
        assert draft[code]["eligible"] is False
        assert draft[code]["record"] is False


def test_reimport_preselects_uploaded_rows_but_keeps_omitted_selection_and_metadata():
    entries = default_entries()
    indexed(entries)["1006"].update(record=False, unit="Eigene Einheit", description="Betreibertext")
    indexed(entries)["9000"]["record"] = False
    before = deepcopy(entries)
    draft = indexed(merge_csv(entries, "Kessel_Ist;4102;1006"))
    assert draft["1006"]["record"] is True
    assert (draft["1006"]["unit"], draft["1006"]["description"]) == ("Eigene Einheit", "Betreibertext")
    assert draft["9000"]["record"] is False
    assert entries == before


def test_one_uploaded_counter_word_preselects_existing_partner_atomically():
    entries = default_entries()
    for code in ("7010", "7011"):
        indexed(entries)[code]["record"] = False
    draft = indexed(merge_csv(entries, "Betrieb_Min;28689;7011"))
    assert draft["7010"]["record"] is True
    assert draft["7011"]["record"] is True
