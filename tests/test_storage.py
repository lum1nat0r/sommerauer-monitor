from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

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
    assert rows[0]["error_code"] is None
    assert rows[0]["error_message"] is None


@pytest.mark.parametrize(
    ("quality", "error_code", "raw_words"),
    [
        ("unavailable", "missing_weather", [32767]),
        ("invalid", "invalid_value", [65535]),
        ("unavailable", "modbus_exception_2", []),
    ],
)
def test_error_observation_replaces_good_current_at_equal_timestamp(
    tmp_path, quality, error_code, raw_words,
):
    store = make_store(tmp_path)
    store.record_cycle(request("good"), [observation("z-good")])
    failed_request = request("failed")
    failed_request.update(offset=4096, register_count=8, outcome="data_error")
    failed = observation("a-error", quality=quality)
    failed.update(
        value=None, raw_words=raw_words, error_code=error_code,
        error_message="Der Wert ist nicht verfügbar; bitte Ursache prüfen.",
        source="failed_reply",
    )
    assert store.record_cycle(failed_request, [failed]) is True

    current = store.current_signals()
    assert len(current) == 1
    assert current[0]["observation_id"] == "a-error"
    assert current[0]["value"] is None
    assert current[0]["quality"] == quality
    assert current[0]["error_code"] == error_code
    assert current[0]["error_message"] == failed["error_message"]
    assert current[0]["raw_words"] == raw_words
    assert current[0]["source"] == "failed_reply"
    assert current[0]["observed_at"] == failed["observed_at"]
    assert current[0]["block_offset"] == 4096
    assert current[0]["register_count"] == 8
    for rows in (
        store.history("boiler.temperature"), store.history_page("boiler.temperature"),
        list(store.stream_observations()),
    ):
        assert len(rows) == 2
        stored = next(row for row in rows if row["observation_id"] == "a-error")
        assert stored == {**failed, "request_id": "failed"}


def test_original_export_survives_sequential_worker_thread_changes(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request("good"), [observation("a-good")])
    invalid = observation("b-invalid", quality="invalid")
    invalid.update(value=None, error_code="invalid_value")
    store.record_cycle(request("bad"), [invalid])
    stream = store.stream_observations()
    with ThreadPoolExecutor(max_workers=1) as first, ThreadPoolExecutor(max_workers=1) as second:
        good = first.submit(next, stream).result()
        bad = second.submit(next, stream).result()
        assert second.submit(next, stream, None).result() is None
    assert (good["value"], good["unit"], good["raw_words"]) == (42, "°C", [42])
    assert (bad["value"], bad["quality"], bad["error_code"]) == (None, "invalid", "invalid_value")


def test_error_cycle_failure_keeps_previous_current_and_can_be_retried(tmp_path):
    store = make_store(tmp_path)
    store.record_cycle(request("good"), [observation("good")])
    failed = observation("failed", quality="invalid")
    failed.update(value=None, error_code="invalid_value", error_message="Ungültiger Wert.")
    corrupt = observation("corrupt", quality="corrupt")
    corrupt["signal_id"] = "buffer.top_temperature"

    with pytest.raises(StorageError):
        store.record_cycle(request("failed-request"), [failed, corrupt])

    assert store.current_signals()[0]["observation_id"] == "good"
    assert store.history("buffer.top_temperature") == []
    assert store.record_cycle(request("failed-request"), [failed]) is True
    assert store.current_signals()[0]["value"] is None


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
    failed = observation("unavailable", quality="unavailable")
    failed.update(
        value=None, error_code="missing_weather",
        error_message="Wetterdaten stehen nicht zur Verfügung.", raw_words=[32767],
    )
    store.record_cycle(request("failed-weather"), [failed])
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

    with pytest.raises(StorageError):
        SQLiteStore(path)
    with pytest.raises(StorageError):
        SQLiteStore.restore_from(path, tmp_path / "unsupported-restore.sqlite3")




@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_database_preserves_minute_values_and_extra_tables_on_restore(tmp_path, version):
    path = tmp_path / "legacy.sqlite3"
    store = SQLiteStore(path)
    start = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)

    def write_minute(target, minute):
        timestamp = (start + timedelta(minutes=minute)).isoformat()
        for signal_id, offset, value in (
            ("boiler.temperature", 4102, 62 + minute),
            ("buffer.top_temperature", 36864, 48 + minute),
        ):
            cycle = request(f"{signal_id}-minute-{minute}")
            cycle.update(started_at=timestamp, completed_at=timestamp, offset=offset)
            row = observation(f"{signal_id}-{minute}")
            row.update(
                signal_id=signal_id, observed_at=timestamp,
                value=value, raw_words=[value],
            )
            assert target.record_cycle(cycle, [row]) is True

    def snapshot(database):
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            tables = [
                row["name"] for row in connection.execute(
                    """SELECT name FROM sqlite_master WHERE type='table'
                    AND name NOT IN ('schema_migrations', 'logging_config')
                    AND name NOT LIKE 'sqlite_%' ORDER BY name"""
                )
            ]
            result = {}
            for table in tables:
                quoted = table.replace('"', '""')
                rows = [
                    dict(row) for row in connection.execute(
                        f'SELECT * FROM "{quoted}" ORDER BY rowid'
                    )
                ]
                if table == "observations":
                    for row in rows:
                        row.setdefault("error_code", None)
                        row.setdefault("error_message", None)
                result[table] = rows
            return result

    for minute in range(3):
        write_minute(store, minute)
    state = {
        "state": "running", "reconnect_attempts": 2,
        "blocked_signals": ["boiler.temperature"],
    }
    store.save_collector_state(state, start.isoformat())
    original_measurements = list(store.stream_observations())
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE observations DROP COLUMN error_code")
        connection.execute("ALTER TABLE observations DROP COLUMN error_message")
        connection.execute("DELETE FROM schema_migrations WHERE version = 4")
        if version < 3:
            connection.execute("DROP TABLE logging_config")
            connection.execute("DELETE FROM schema_migrations WHERE version = 3")
        connection.execute(f"PRAGMA user_version = {version}")
    if version == 2:
        # Synthetische additive Alttabellen dürfen weder migriert noch gelöscht werden.
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE diagnostic_runs (
                        run_id TEXT PRIMARY KEY NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        requests_reserved INTEGER NOT NULL,
                        started_at TEXT NULL,
                        ended_at TEXT NULL,
                        stop_reason TEXT NULL,
                        acknowledged_at TEXT NULL,
                        resolution_note TEXT NULL
                    );
                    CREATE UNIQUE INDEX diagnostic_one_active
                        ON diagnostic_runs ((1))
                        WHERE state IN ('running', 'awaiting_review');
                    CREATE TABLE diagnostic_requests (
                        run_id TEXT REFERENCES diagnostic_runs,
                        step_index INTEGER,
                        outcome TEXT,
                        started_at TEXT,
                        completed_at TEXT NULL,
                        raw_words_json TEXT NULL,
                        decoded_json TEXT NULL,
                        error_class TEXT NULL,
                        received_bytes INTEGER,
                        review_json TEXT NULL,
                        PRIMARY KEY (run_id, step_index)
                    );
                    CREATE TABLE control_plans (
                        plan_id TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        document_json TEXT NOT NULL,
                        PRIMARY KEY (plan_id, revision)
                    );
                    INSERT INTO diagnostic_runs VALUES (
                        'synthetic-run', '2026-10-14T11:00:00+00:00',
                        '2026-10-14T11:01:00+00:00', '{"synthetic":true}', 'completed', 1,
                        '2026-10-14T11:00:00+00:00', '2026-10-14T11:01:00+00:00',
                        NULL, NULL, NULL
                    );
                    INSERT INTO diagnostic_requests VALUES (
                        'synthetic-run', 0, 'ok', '2026-10-14T11:00:00+00:00',
                        '2026-10-14T11:00:01+00:00', '[62]', '{"synthetic":true}',
                        NULL, 7, NULL
                    );
                    INSERT INTO control_plans VALUES (
                        'synthetic-plan', 1, '2026-10-14T11:00:00+00:00',
                        '{"synthetic":true}'
                    );
                    INSERT INTO schema_migrations
                        VALUES (2, '2026-10-14T11:00:00+00:00');
                    PRAGMA user_version = 2;
                    """
                )

    original = snapshot(path)
    legacy_backup = tmp_path / "legacy-backup.sqlite3"
    store.backup_to(legacy_backup)
    legacy_backup_bytes = legacy_backup.read_bytes()
    legacy_restored = SQLiteStore.restore_from(
        legacy_backup, tmp_path / "legacy-restored.sqlite3",
    )
    assert list(legacy_restored.stream_observations()) == original_measurements
    assert legacy_restored.get_collector_state() == {**state, "state": "paused"}
    assert legacy_backup.read_bytes() == legacy_backup_bytes
    assert snapshot(path) == original
    reopened = SQLiteStore(path)
    assert snapshot(path) == original
    assert reopened.get_logging_config()["revision"] == 0
    assert list(reopened.stream_observations()) == original_measurements
    write_minute(reopened, 3)
    measurements = list(reopened.stream_observations())
    assert len(measurements) == 8
    assert measurements[:6] == original_measurements
    assert [row["value"] for row in measurements] == [62, 48, 63, 49, 64, 50, 65, 51]

    source_snapshot = snapshot(path)
    backup = tmp_path / "backup.sqlite3"
    reopened.backup_to(backup)
    assert snapshot(backup) == source_snapshot
    backup_bytes = backup.read_bytes()
    restored = SQLiteStore.restore_from(backup, tmp_path / "restored.sqlite3")

    assert backup.read_bytes() == backup_bytes
    assert snapshot(backup) == source_snapshot
    assert snapshot(path) == source_snapshot
    assert reopened.get_collector_state() == state
    assert list(restored.stream_observations()) == measurements
    assert restored.get_collector_state() == {**state, "state": "paused"}
    assert {
        table: rows for table, rows in snapshot(restored.path).items()
        if table != "collector_state"
    } == {
        table: rows for table, rows in source_snapshot.items()
        if table != "collector_state"
    }
    for database in (path, backup, restored.path):
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    write_minute(restored, 4)
    assert restored.count_observations() == 10
    assert snapshot(path) == source_snapshot
    assert backup.read_bytes() == backup_bytes


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
            """INSERT INTO observations
            (observation_id, request_id, signal_id, observed_at, value, unit, quality,
             raw_words_json, source, profile_id, profile_version, decoder_version) VALUES
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
