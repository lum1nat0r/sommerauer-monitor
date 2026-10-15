from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from threading import Barrier
from uuid import UUID

import sqlite3

import pytest

from backend.storage import SCHEMA_VERSION, SQLiteStore, StorageError


def make_store(tmp_path):
    return SQLiteStore(tmp_path / "monitor.sqlite3")


def request(request_id="request-1"):
    return {
        "request_id": request_id,
        "started_at": "2026-10-14T12:00:00+00:00",
        "completed_at": "2026-10-14T12:00:01+00:00",
        "function_code": 3,
        "unit_id": 255,
        "offset": 4102,
        "register_count": 1,
        "outcome": "ok",
    }


def observation(observation_id="observation-1", quality="ok"):
    return {
        "observation_id": observation_id,
        "signal_id": "boiler.temperature",
        "observed_at": "2026-10-14T12:00:01+00:00",
        "value": 42,
        "unit": "°C",
        "quality": quality,
        "raw_words": [42],
        "source": "modbus_fc03",
        "profile_id": "core",
        "profile_version": "1",
        "decoder_version": "1",
    }


def test_atomic_cycle_keeps_provenance_and_duplicate_retry_is_noop(tmp_path):
    store = make_store(tmp_path)

    assert store.record_cycle(request(), [observation()]) is True
    assert store.record_cycle(request(), [observation()]) is False

    rows = store.history("boiler.temperature")
    assert len(rows) == 1
    assert (rows[0]["value"], rows[0]["quality"], rows[0]["raw_words"]) == (42, "ok", [42])
    assert (rows[0]["source"], rows[0]["profile_version"], rows[0]["decoder_version"]) == (
        "modbus_fc03", "1", "1"
    )


def test_failed_cycle_rolls_back_request_and_any_prior_observations(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(StorageError, match="Could not store acquisition"):
        store.record_cycle(request(), [observation(), observation("bad", quality="corrupt")])

    assert store.history("boiler.temperature") == []
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0


def test_backup_and_restore_preserve_history_and_pause_collector(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request(), [observation()])
    store.record_event("event-1", "2026-10-14T12:01:00+00:00", "connected", "info", "ok")
    store.save_config(1, {"collector_enabled": False}, "2026-10-14T12:00:00+00:00")
    store.save_collector_state({"state": "running", "attempts": 2}, "2026-10-14T12:00:00+00:00")
    backup = tmp_path / "backup.sqlite3"
    store.backup_to(backup)
    restored = SQLiteStore.restore_from(backup, tmp_path / "restored.sqlite3")

    assert restored.history("boiler.temperature") == store.history("boiler.temperature")
    assert restored.get_collector_state() == {"attempts": 2, "state": "paused"}
    with sqlite3.connect(restored.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_migration_reopen_preserves_rows_and_rejects_newer_schema(tmp_path):
    path = tmp_path / "monitor.sqlite3"
    store = SQLiteStore(path)
    store.record_cycle(request(), [observation()])
    assert SQLiteStore(path).history("boiler.temperature") == store.history("boiler.temperature")
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(StorageError, match="newer than supported"):
        SQLiteStore(path)


def test_history_uses_half_open_bounds_and_enforces_point_limit(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request("first"), [observation("obs-first")])
    second_request = request("second")
    second_request["started_at"] = "2026-10-14T12:01:00+00:00"
    second = observation("obs-second")
    second["observed_at"] = "2026-10-14T12:01:01+00:00"
    store.record_cycle(second_request, [second])

    rows = store.history("boiler.temperature", start="2026-10-14T12:00:00+00:00", end="2026-10-14T12:01:01+00:00")
    assert [row["observation_id"] for row in rows] == ["obs-first"]
    with pytest.raises(ValueError, match="1..10000"):
        store.history("boiler.temperature", limit=0)


def test_database_size_includes_wal_and_unwritable_path_fails(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request(), [observation()])
    assert store.disk_usage_bytes() > 0

    blocked = tmp_path / "file-not-directory"
    blocked.write_text("not a directory")
    with pytest.raises(StorageError, match="Could not initialize database"):
        SQLiteStore(blocked / "monitor.sqlite3")

def test_large_synthetic_history_is_retained_and_query_is_bounded(tmp_path):
    store = make_store(tmp_path)
    with sqlite3.connect(store.path) as connection:
        connection.executemany(
            "INSERT INTO requests VALUES (?, ?, NULL, 3, 255, 4102, 1, 'ok', NULL)",
            [
                (f"bulk-request-{index:05}", "2026-10-14T00:00:00+00:00")
                for index in range(10_050)
            ],
        )
        connection.execute(
            "INSERT INTO signals VALUES ('boiler.temperature', '°C', '{}')"
        )
        connection.executemany(
            """INSERT INTO observations VALUES
            (?, ?, 'boiler.temperature', ?, 42, '°C', 'ok', '[42]',
             'modbus_fc03', 'core', '1', '1')""",
            [
                (
                    f"bulk-{index:05}",
                    f"bulk-request-{index:05}",
                    f"2026-10-14T{index // 3600:02}:{(index // 60) % 60:02}:{index % 60:02}+00:00",
                )
                for index in range(10_050)
            ],
        )

    rows = store.history("boiler.temperature", limit=10_000)
    assert len(rows) == 10_000
    assert rows[0]["observation_id"] == "bulk-00000"
    assert rows[-1]["observation_id"] == "bulk-09999"
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 10_050

def test_full_database_write_is_reported_as_storage_error(tmp_path):
    store = make_store(tmp_path)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """CREATE TRIGGER simulate_full BEFORE INSERT ON events
            BEGIN SELECT RAISE(ABORT, 'database or disk is full'); END"""
        )

    with pytest.raises(StorageError, match="Could not store event"):
        store.record_event(
            "full-disk",
            "2026-10-14T12:00:00+00:00",
            "diagnostic",
            "error",
            "x" * 200_000,
        )

def test_restore_rejects_unversioned_empty_file(tmp_path):
    backup = tmp_path / "empty.sqlite3"
    sqlite3.connect(backup).close()

    with pytest.raises(StorageError, match="Backup schema 0 is not supported"):
        SQLiteStore.restore_from(backup, tmp_path / "restore" / "monitor.sqlite3")


DIAGNOSTIC_TIME = "2026-10-15T12:00:00+00:00"
HISTORY_TABLES = (
    "profiles", "signals", "requests", "observations", "events",
    "config_versions", "collector_state",
)


def diagnostic_plan(steps=2):
    offsets = [4102, 33408, 4098][:steps]
    binding = {
        "host": "offline.invalid",
        "port": 502,
        "unit_id": 255,
        "source": "simulator",
        "catalog_sha256": "a" * 64,
    }
    return {
        "schema_version": 1,
        "catalog_sha256": binding["catalog_sha256"],
        "register_ids": [f"register:{offset}" for offset in offsets],
        "blocks": [{"offset": offset, "count": 1} for offset in offsets],
        "purpose": "Synthetische Offline-Prüfung",
        "source": "simulator",
        "target": {"host": binding["host"], "port": binding["port"]},
        "target_fingerprint": hashlib.sha256(
            json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "function_code": 3,
        "unit_id": 255,
        "deadline_seconds": 3,
        "request_budget": steps,
        "min_interval_seconds": 60,
        "max_duration_seconds": 600,
        "stop_conditions": [
            "transport", "protocol", "data", "storage", "operator", "anomaly", "expired",
        ],
    }


def diagnostic_result(**changes):
    result = {
        "outcome": "ok",
        "raw_words": [110],
        "decoded": None,
        "error_class": None,
        "received_bytes": 11,
        "completed_at": "2026-10-15T12:00:01+00:00",
    }
    result.update(changes)
    return result


def reserve(store, run_id, step=0):
    store.reserve_diagnostic_request(run_id, step, DIAGNOSTIC_TIME)


def answered_run(store, steps=2):
    run = store.create_diagnostic_run(diagnostic_plan(steps))
    reserve(store, run["run_id"])
    store.finish_diagnostic_request(
        run["run_id"], 0,
        diagnostic_result(raw_words=[42], decoded={"boiler.temperature": 42}),
        "awaiting_review",
    )
    return run["run_id"]


def database_rows(path, tables=HISTORY_TABLES):
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in tables
        }


def synthetic_v1(path):
    """Eine echte v1-Datei samt vollständiger historischer Nutzdaten herstellen."""
    store = SQLiteStore(path)
    store.record_cycle(request(), [observation()])
    store.record_cycle(request("request-2"), [observation("observation-2", "invalid")])
    store.record_event("historic-event", DIAGNOSTIC_TIME, "connected", "info", "synthetisch")
    store.save_config(1, {"collector_enabled": False}, DIAGNOSTIC_TIME)
    store.save_collector_state({"state": "paused", "attempts": 7}, DIAGNOSTIC_TIME)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE signals SET definition_json = ?",
            ('{"signal_id":"boiler.temperature","synthetic":"unverändert"}',),
        )
        connection.execute(
            "UPDATE profiles SET definition_json = ?",
            ('{"profile_id":"core","version":"1","synthetic":[1,2]}',),
        )
        connection.execute("DROP INDEX diagnostic_one_active")
        connection.execute("DROP TABLE diagnostic_requests")
        connection.execute("DROP TABLE diagnostic_runs")
        connection.execute("DROP TABLE control_plans")
        connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        connection.execute("PRAGMA user_version = 1")
    return database_rows(path)


def assert_utc(value):
    assert datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() == timedelta(0)


def test_v1_upgrade_preserves_every_historical_column(tmp_path):
    path = tmp_path / "v1.sqlite3"
    before = synthetic_v1(path)
    upgraded = SQLiteStore(path)
    assert database_rows(path) == before
    run = upgraded.create_diagnostic_run(diagnostic_plan())
    reserve(upgraded, run["run_id"])
    assert upgraded.get_diagnostic_run(run["run_id"])["requests_reserved"] == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,)]
        connection.execute(
            "INSERT INTO control_plans VALUES ('offline-control', 1, ?, '{}')",
            (DIAGNOSTIC_TIME,),
        )
    assert database_rows(path) == before


def test_failed_v1_migration_rolls_back_schema_and_history(tmp_path):
    path = tmp_path / "collision.sqlite3"
    before = synthetic_v1(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE control_plans (sentinel TEXT)")
        connection.execute("INSERT INTO control_plans VALUES ('unverändert')")
        schema_before = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    with pytest.raises(StorageError):
        SQLiteStore(path)
    assert database_rows(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
        assert connection.execute("SELECT * FROM control_plans").fetchall() == [("unverändert",)]
        assert connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall() == schema_before


def test_private_plan_snapshot_uuid_utc_and_pagination(tmp_path):
    store = make_store(tmp_path)
    original = diagnostic_plan()
    expected = deepcopy(original)
    first = store.create_diagnostic_run(original)
    run_id = first["run_id"]
    assert UUID(run_id).version == 4
    assert first["state"] == "planned"
    assert first["requests_reserved"] == 0
    assert first["requests"] == []
    assert first["plan"] == expected
    for field in ("created_at", "updated_at"):
        assert_utc(first[field])
    original["target"]["host"] = "changed.invalid"
    original["blocks"][0]["offset"] = 999
    first["plan"]["target"]["port"] = 999
    assert store.get_diagnostic_run(run_id)["plan"] == expected
    assert store.get_diagnostic_run("missing-run") is None
    for _ in range(4):
        store.create_diagnostic_run(diagnostic_plan(1))
    all_runs = store.list_diagnostic_runs(20, 0)
    assert len({run["run_id"] for run in all_runs}) == 5
    assert store.list_diagnostic_runs(2, 0) + store.list_diagnostic_runs(2, 2) == all_runs[:4]
    assert store.list_diagnostic_runs(2, 4) == all_runs[4:]
    assert store.list_diagnostic_runs(2, 5) == []
    listed = next(run for run in all_runs if run["run_id"] == run_id)
    assert listed["plan"] == expected
    listed["plan"]["blocks"].clear()
    reserve(store, run_id)
    stored = store.get_diagnostic_run(run_id)
    assert stored["plan"] == expected
    assert_utc(stored["started_at"])
    assert_utc(stored["requests"][0]["started_at"])


def simultaneous(*operations):
    barrier = Barrier(len(operations))

    def attempt(operation):
        barrier.wait(timeout=10)
        try:
            operation()
        except StorageError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(attempt, operation) for operation in operations]
        return [future.result(timeout=15) for future in futures]


def test_two_store_starts_allow_only_one_volume_owner(tmp_path):
    first = make_store(tmp_path)
    second = SQLiteStore(first.path)
    runs = [first.create_diagnostic_run(diagnostic_plan()) for _ in range(2)]
    outcomes = simultaneous(
        lambda: first.set_diagnostic_run_state(runs[0]["run_id"], "running", None),
        lambda: second.set_diagnostic_run_state(runs[1]["run_id"], "running", None),
    )
    assert sorted(outcomes) == [False, True]
    saved = first.list_diagnostic_runs(10, 0)
    assert sorted(run["state"] for run in saved) == ["planned", "running"]
    assert first.diagnostic_access_blocker() is not None
    loser = next(run for run in saved if run["state"] == "planned")
    with pytest.raises(StorageError):
        reserve(second, loser["run_id"])
    with pytest.raises(StorageError):
        second.create_diagnostic_run(diagnostic_plan())


def test_two_stores_reserve_same_step_exactly_once(tmp_path):
    first = make_store(tmp_path)
    second = SQLiteStore(first.path)
    run_id = first.create_diagnostic_run(diagnostic_plan())["run_id"]
    assert first.has_diagnostic_requests() is False
    outcomes = simultaneous(
        lambda: reserve(first, run_id),
        lambda: reserve(second, run_id),
    )
    assert sorted(outcomes) == [False, True]
    saved = second.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 1
    assert len(saved["requests"]) == 1
    row = saved["requests"][0]
    assert row["outcome"] == "reserved"
    assert row["received_bytes"] == 0
    assert row["completed_at"] is None
    assert row["raw_words"] is None
    assert row["decoded"] is None
    assert row["review"] is None
    assert first.has_diagnostic_requests() is True
    for step in (-1, 0, 1, 2):
        with pytest.raises(StorageError):
            reserve(first, run_id, step)
    assert first.get_diagnostic_run(run_id)["requests_reserved"] == 1


@pytest.mark.parametrize("awaiting_review", [False, True])
def test_restart_recovery_preserves_consumed_budget_and_answer(tmp_path, awaiting_review):
    store = make_store(tmp_path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(store, run_id)
    if awaiting_review:
        store.finish_diagnostic_request(run_id, 0, diagnostic_result(), "awaiting_review")
    before = store.get_diagnostic_run(run_id)
    del store
    reopened = SQLiteStore(tmp_path / "monitor.sqlite3")
    assert reopened.get_diagnostic_run(run_id) == before
    reopened.interrupt_active_diagnostic_runs()
    saved = reopened.get_diagnostic_run(run_id)
    assert saved["state"] == "interrupted"
    assert saved["requests"] == before["requests"]
    assert saved["requests_reserved"] == 1
    assert reopened.has_diagnostic_requests() is True
    assert reopened.diagnostic_access_blocker() is not None
    for operation in (
        lambda: reserve(reopened, run_id, 1),
        lambda: reopened.set_diagnostic_run_state(run_id, "running", None),
        lambda: reopened.create_diagnostic_run(diagnostic_plan()),
    ):
        with pytest.raises(StorageError):
            operation()
    reopened.acknowledge_diagnostic_run(run_id, "Ursache offline geklärt")
    assert reopened.diagnostic_access_blocker() is None
    assert reopened.get_diagnostic_run(run_id)["requests_reserved"] == 1
    with pytest.raises(StorageError):
        reopened.set_diagnostic_run_state(run_id, "running", None)
    next_id = reopened.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(reopened, next_id)
    assert reopened.get_diagnostic_run(next_id)["requests_reserved"] == 1


@pytest.mark.parametrize("steps", [1, 2])
@pytest.mark.parametrize(
    ("verdict", "expected"), [("continue", None), ("finish", "cancelled"), ("anomaly", "stopped_data")]
)
def test_review_is_separate_and_controls_next_manual_step(tmp_path, steps, verdict, expected):
    store = make_store(tmp_path)
    run_id = answered_run(store, steps)
    before = store.get_diagnostic_run(run_id)
    assert before["state"] == "awaiting_review"
    with pytest.raises(StorageError):
        reserve(store, run_id, 1)
    review = {"verdict": verdict, "observation": "Synthetische Sichtprüfung"}
    expected = expected or ("completed" if steps == 1 else "running")
    store.review_diagnostic_request(run_id, 0, review, expected)
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == expected
    assert saved["plan"] == before["plan"]
    answer = saved["requests"][0]
    assert answer["review"] == review
    assert {key: value for key, value in answer.items() if key != "review"} == {
        key: value for key, value in before["requests"][0].items() if key != "review"
    }
    with pytest.raises(StorageError):
        store.review_diagnostic_request(run_id, 0, review, expected)
    with pytest.raises(StorageError):
        store.finish_diagnostic_request(run_id, 0, diagnostic_result(raw_words=[999]), expected)
    if expected == "running":
        reserve(store, run_id, 1)
        store.finish_diagnostic_request(run_id, 1, diagnostic_result(), "awaiting_review")
        store.review_diagnostic_request(
            run_id, 1, {"verdict": "continue", "observation": None}, "completed"
        )
        assert store.get_diagnostic_run(run_id)["requests_reserved"] == steps
    else:
        assert_utc(saved["ended_at"])
    with pytest.raises(StorageError):
        reserve(store, run_id, steps)
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == (
        steps if expected == "running" else 1
    )
    assert (store.diagnostic_access_blocker() is not None) == (verdict == "anomaly")


def test_decoder_failure_keeps_exact_raw_110_without_core_observations(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request(), [observation()])
    before = database_rows(store.path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(store, run_id)
    result = diagnostic_result(outcome="error", decoded=None, error_class="DecoderError")
    store.finish_diagnostic_request(run_id, 0, result, "stopped_data")
    result["raw_words"][0] = 999
    saved = store.get_diagnostic_run(run_id)
    assert saved["requests"][0]["raw_words"] == [110]
    assert saved["requests"][0]["decoded"] is None
    assert saved["requests"][0]["review"] is None
    assert saved["requests"][0]["error_class"] == "DecoderError"
    assert saved["requests"][0]["received_bytes"] == 11
    assert database_rows(store.path) == before
    assert_utc(saved["requests"][0]["completed_at"])


@pytest.mark.parametrize("state", [
    "interrupted", "stopped_transport", "stopped_protocol", "stopped_data", "stopped_storage",
])
def test_hard_stop_requires_nonempty_ack_and_never_reactivates_old_id(tmp_path, state):
    store = make_store(tmp_path)
    waiting = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(store, run_id)
    store.set_diagnostic_run_state(run_id, state, "Synthetische Ursache")
    before = store.get_diagnostic_run(run_id)
    for resolution in ("", "   "):
        with pytest.raises(StorageError):
            store.acknowledge_diagnostic_run(run_id, resolution)
    assert store.get_diagnostic_run(run_id) == before
    assert store.diagnostic_access_blocker() is not None
    for operation in (
        lambda: store.create_diagnostic_run(diagnostic_plan()),
        lambda: reserve(store, waiting),
        lambda: store.set_diagnostic_run_state(waiting, "running", None),
    ):
        with pytest.raises(StorageError):
            operation()
    store.acknowledge_diagnostic_run(run_id, "Ursache geprüft")
    after = store.get_diagnostic_run(run_id)
    assert_utc(after["acknowledged_at"])
    assert after["resolution_note"] == "Ursache geprüft"
    assert after["state"] == state
    assert after["requests_reserved"] == 1
    assert after["requests"] == before["requests"]
    assert store.diagnostic_access_blocker() is None
    for target in ("planned", "running", "awaiting_review"):
        with pytest.raises(StorageError):
            store.set_diagnostic_run_state(run_id, target, None)
    reserve(store, waiting)


@pytest.mark.parametrize("soft_stop", ["cancelled", "expired"])
@pytest.mark.parametrize("hard_first", [False, True])
def test_late_finish_keeps_hard_failure_over_stop_or_expiry(tmp_path, soft_stop, hard_first):
    store = make_store(tmp_path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(store, run_id)

    def finish():
        store.finish_diagnostic_request(
            run_id, 0, diagnostic_result(outcome="error", decoded=None, error_class="ProtocolError"),
            "stopped_protocol",
        )

    if hard_first:
        finish()
    try:
        store.set_diagnostic_run_state(run_id, soft_stop, "Betreiberstopp oder Ablauf")
    except StorageError:
        assert hard_first
    if not hard_first:
        finish()
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == "stopped_protocol"
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["error_class"] == "ProtocolError"
    assert saved["requests"][0]["raw_words"] == [110]
    assert store.diagnostic_access_blocker() is not None


@pytest.mark.parametrize("table", ["diagnostic_runs", "diagnostic_requests"])
@pytest.mark.parametrize("operation", ["reserve", "finish", "review"])
def test_sql_write_failure_rolls_back_entire_diagnostic_operation(tmp_path, operation, table):
    store = make_store(tmp_path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    if operation in ("finish", "review"):
        reserve(store, run_id)
    if operation == "review":
        store.finish_diagnostic_request(run_id, 0, diagnostic_result(), "awaiting_review")
    before = store.get_diagnostic_run(run_id)
    # Beide Schreibrichtungen prüfen: keine halbe Reservierung/Antwort/Bewertung.
    action = "INSERT" if table == "diagnostic_requests" and operation == "reserve" else "UPDATE"
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            f"""CREATE TRIGGER synthetic_disk_failure BEFORE {action} ON {table}
            BEGIN SELECT RAISE(ABORT, 'synthetic disk full'); END"""
        )
    with pytest.raises(StorageError):
        if operation == "reserve":
            reserve(store, run_id)
        elif operation == "finish":
            store.finish_diagnostic_request(run_id, 0, diagnostic_result(), "awaiting_review")
        else:
            store.review_diagnostic_request(
                run_id, 0, {"verdict": "continue", "observation": None}, "running"
            )
    assert store.get_diagnostic_run(run_id) == before
    assert store.has_diagnostic_requests() == (operation != "reserve")
    if operation != "reserve":
        assert store.diagnostic_access_blocker() is not None
        with pytest.raises(StorageError):
            reserve(store, run_id, 1)
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER synthetic_disk_failure")
    if operation == "reserve":
        reserve(store, run_id)
    elif operation == "finish":
        store.finish_diagnostic_request(run_id, 0, diagnostic_result(), "awaiting_review")
    else:
        store.review_diagnostic_request(
            run_id, 0, {"verdict": "continue", "observation": None}, "running"
        )
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1


def test_v1_restore_migrates_only_copy_and_preserves_complete_history(tmp_path):
    backup = tmp_path / "v1-backup.sqlite3"
    before = synthetic_v1(backup)
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    restored = SQLiteStore.restore_from(backup, tmp_path / "v1-restored.sqlite3")
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == digest
    assert database_rows(restored.path) == before
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    run_id = restored.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(restored, run_id)
    assert restored.get_diagnostic_run(run_id)["requests_reserved"] == 1


@pytest.mark.parametrize("active_state", ["running", "awaiting_review"])
def test_v2_restore_preserves_plans_answers_all_control_revisions_and_blockers(tmp_path, active_state):
    store = make_store(tmp_path)
    store.record_cycle(request(), [observation()])
    planned_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    stopped_id = answered_run(store)
    store.review_diagnostic_request(
        stopped_id, 0, {"verdict": "anomaly", "observation": "synthetisch"}, "stopped_data"
    )
    store.acknowledge_diagnostic_run(stopped_id, "Vor Backup quittiert")
    active_id = store.create_diagnostic_run(diagnostic_plan(3))["run_id"]
    reserve(store, active_id)
    if active_state == "awaiting_review":
        store.finish_diagnostic_request(active_id, 0, diagnostic_result(), "awaiting_review")
    revisions = [
        ("synthetic-control", 1, DIAGNOSTIC_TIME, '{"value":1}'),
        ("synthetic-control", 2, DIAGNOSTIC_TIME, '{"value":2}'),
        ("other-control", 1, DIAGNOSTIC_TIME, '{"value":3}'),
    ]
    with sqlite3.connect(store.path) as connection:
        connection.executemany("INSERT INTO control_plans VALUES (?, ?, ?, ?)", revisions)
    before = {run["run_id"]: run for run in store.list_diagnostic_runs(20, 0)}
    historical = database_rows(store.path)
    backup = tmp_path / "v2-backup.sqlite3"
    store.backup_to(backup)
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    restored = SQLiteStore.restore_from(backup, tmp_path / "v2-restored.sqlite3")
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == digest
    assert database_rows(restored.path) == historical
    assert restored.get_diagnostic_run(planned_id) == before[planned_id]
    assert restored.get_diagnostic_run(stopped_id) == before[stopped_id]
    active = restored.get_diagnostic_run(active_id)
    assert active["state"] == "interrupted"
    assert active["plan"] == before[active_id]["plan"]
    assert active["requests"] == before[active_id]["requests"]
    assert active["requests_reserved"] == 1
    assert restored.has_diagnostic_requests() is True
    assert restored.diagnostic_access_blocker() is not None
    for candidate in (active_id, planned_id):
        with pytest.raises(StorageError):
            reserve(restored, candidate, 0 if candidate == planned_id else 1)
    with pytest.raises(StorageError):
        restored.create_diagnostic_run(diagnostic_plan())
    with sqlite3.connect(restored.path) as connection:
        assert connection.execute(
            "SELECT * FROM control_plans ORDER BY rowid"
        ).fetchall() == revisions
    restored.acknowledge_diagnostic_run(active_id, "Restore geprüft, kein Neustart")
    assert restored.get_diagnostic_run(active_id)["state"] == "interrupted"
    assert restored.get_diagnostic_run(active_id)["requests_reserved"] == 1
    assert restored.diagnostic_access_blocker() is None
    reserve(restored, planned_id)


@pytest.mark.parametrize("version", [0, SCHEMA_VERSION + 1])
def test_restore_rejects_unsupported_version_without_touching_backup(tmp_path, version):
    backup = tmp_path / "unsupported.sqlite3"
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE synthetic (value TEXT)")
        connection.execute("INSERT INTO synthetic VALUES ('unverändert')")
        connection.execute(f"PRAGMA user_version = {version}")
    before = backup.read_bytes()
    with pytest.raises(StorageError):
        SQLiteStore.restore_from(backup, tmp_path / "rejected.sqlite3")
    assert backup.read_bytes() == before


def test_restore_refuses_existing_volume_without_mutating_it(tmp_path):
    source = SQLiteStore(tmp_path / "source.sqlite3")
    backup = tmp_path / "backup.sqlite3"
    source.backup_to(backup)
    target = SQLiteStore(tmp_path / "in-use.sqlite3")
    run_id = target.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(target, run_id)
    before = target.get_diagnostic_run(run_id)
    backup_before = backup.read_bytes()
    with pytest.raises(StorageError):
        SQLiteStore.restore_from(backup, target.path)
    assert target.get_diagnostic_run(run_id) == before
    assert target.diagnostic_access_blocker() is not None
    assert backup.read_bytes() == backup_before


def test_three_step_budget_survives_reopening_without_reset(tmp_path):
    store = make_store(tmp_path)
    plan = diagnostic_plan(3)
    run_id = store.create_diagnostic_run(plan)["run_id"]
    for step in range(3):
        store = SQLiteStore(store.path)
        assert store.get_diagnostic_run(run_id)["requests_reserved"] == step
        reserve(store, run_id, step)
        store.finish_diagnostic_request(run_id, step, diagnostic_result(), "awaiting_review")
        store.review_diagnostic_request(
            run_id, step, {"verdict": "continue", "observation": None},
            "completed" if step == 2 else "running",
        )
    saved = SQLiteStore(store.path).get_diagnostic_run(run_id)
    assert saved["state"] == "completed"
    assert saved["requests_reserved"] == 3
    assert saved["plan"] == plan
    assert [row["step_index"] for row in saved["requests"]] == [0, 1, 2]
    for step in (0, 1, 2, 3):
        with pytest.raises(StorageError):
            reserve(store, run_id, step)
    assert store.get_diagnostic_run(run_id) == saved
    assert store.has_diagnostic_requests() is True
    assert store.diagnostic_access_blocker() is None


def test_timestamp_offsets_normalize_to_utc_and_missing_finish_time_is_generated(tmp_path):
    store = make_store(tmp_path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    store.reserve_diagnostic_request(run_id, 0, "2026-10-15T14:00:00+02:00")
    result = diagnostic_result()
    del result["completed_at"]
    store.finish_diagnostic_request(run_id, 0, result, "awaiting_review")
    row = store.get_diagnostic_run(run_id)["requests"][0]
    assert datetime.fromisoformat(row["started_at"]) == datetime.fromisoformat(DIAGNOSTIC_TIME)
    assert_utc(row["started_at"])
    assert_utc(row["completed_at"])


@pytest.mark.parametrize("soft_stop", ["cancelled", "expired"])
def test_concurrent_operator_stop_and_error_finish_never_soften_failure(tmp_path, soft_stop):
    first = make_store(tmp_path)
    second = SQLiteStore(first.path)
    run_id = first.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(first, run_id)
    results = simultaneous(
        lambda: first.finish_diagnostic_request(
            run_id, 0, diagnostic_result(outcome="error", decoded=None, error_class="TransportError"),
            "stopped_transport",
        ),
        lambda: second.set_diagnostic_run_state(run_id, soft_stop, "Synthetischer Stopp"),
    )
    assert results[0] is True
    saved = second.get_diagnostic_run(run_id)
    assert saved["state"] == "stopped_transport"
    assert saved["requests_reserved"] == 1
    assert saved["requests"][0]["error_class"] == "TransportError"
    assert second.diagnostic_access_blocker() is not None


def test_fresh_migration_failure_also_rolls_back_v1_tables(tmp_path):
    path = tmp_path / "fresh-collision.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE control_plans (original TEXT)")
        connection.execute("INSERT INTO control_plans VALUES ('erhalten')")
        before = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    with pytest.raises(StorageError):
        SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall() == before
        assert connection.execute("SELECT * FROM control_plans").fetchall() == [("erhalten",)]


def test_unconfirmed_raw_block_cannot_persist_interpreted_measurement(tmp_path):
    store = make_store(tmp_path)
    plan = diagnostic_plan(1)
    plan["register_ids"] = ["register:33408"]
    plan["blocks"] = [{"offset": 33408, "count": 1}]
    run_id = store.create_diagnostic_run(plan)["run_id"]
    reserve(store, run_id)
    before = store.get_diagnostic_run(run_id)
    with pytest.raises(StorageError):
        store.finish_diagnostic_request(
            run_id, 0, diagnostic_result(decoded={"temperature": 42}), "awaiting_review"
        )
    assert store.get_diagnostic_run(run_id) == before
    store.finish_diagnostic_request(run_id, 0, diagnostic_result(), "awaiting_review")
    assert store.get_diagnostic_run(run_id)["requests"][0]["decoded"] is None
    assert store.count_observations() == 0


def test_late_hard_error_requires_new_acknowledgement_after_recovery_ack(tmp_path):
    store = make_store(tmp_path)
    run_id = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    reserve(store, run_id)
    store.interrupt_active_diagnostic_runs()
    store.acknowledge_diagnostic_run(run_id, "Unterbrechung geprüft")
    waiting = store.create_diagnostic_run(diagnostic_plan())["run_id"]
    store.finish_diagnostic_request(
        run_id, 0, diagnostic_result(outcome="error", error_class="ProtocolError"),
        "stopped_protocol",
    )
    saved = store.get_diagnostic_run(run_id)
    assert saved["state"] == "stopped_protocol"
    assert saved["acknowledged_at"] is None
    assert saved["resolution_note"] is None
    with pytest.raises(StorageError):
        reserve(store, waiting)
    store.acknowledge_diagnostic_run(run_id, "Protokollfehler zusätzlich geklärt")
    reserve(store, waiting)
    assert store.get_diagnostic_run(run_id)["requests_reserved"] == 1
