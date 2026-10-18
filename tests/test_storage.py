from contextlib import closing
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

    with pytest.raises(StorageError):
        SQLiteStore(path)
    with pytest.raises(StorageError):
        SQLiteStore.restore_from(path, tmp_path / "unsupported-restore.sqlite3")




@pytest.mark.parametrize("version", [1, 2])
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

    def dump(database):
        with closing(sqlite3.connect(database)) as connection:
            return list(connection.iterdump())

    def legacy_dump(database):
        return [
            line for line in dump(database)
            if "logging_config" not in line
            and not line.startswith('INSERT INTO "schema_migrations"')
        ]

    for minute in range(3):
        write_minute(store, minute)
    state = {"state": "running", "attempts": 2}
    store.save_collector_state(state, start.isoformat())
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE logging_config")
        connection.execute("DELETE FROM schema_migrations WHERE version = 3")
        connection.execute("PRAGMA user_version = 1")
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

    original = legacy_dump(path)
    original_measurements = list(store.stream_observations())
    reopened = SQLiteStore(path)
    assert legacy_dump(path) == original
    assert reopened.get_logging_config()["revision"] == 0
    assert list(reopened.stream_observations()) == original_measurements
    write_minute(reopened, 3)
    measurements = list(reopened.stream_observations())
    assert len(measurements) == 8
    assert measurements[:6] == original_measurements
    assert [row["value"] for row in measurements] == [62, 48, 63, 49, 64, 50, 65, 51]

    source_dump = dump(path)
    backup = tmp_path / "backup.sqlite3"
    reopened.backup_to(backup)
    assert dump(backup) == source_dump
    backup_bytes = backup.read_bytes()
    restored = SQLiteStore.restore_from(backup, tmp_path / "restored.sqlite3")

    assert backup.read_bytes() == backup_bytes
    assert dump(backup) == source_dump
    assert dump(path) == source_dump
    assert reopened.get_collector_state() == state
    assert list(restored.stream_observations()) == measurements
    assert restored.get_collector_state() == {"state": "paused", "attempts": 2}
    assert [
        line for line in dump(restored.path)
        if not line.startswith('INSERT INTO "collector_state"')
    ] == [
        line for line in source_dump
        if not line.startswith('INSERT INTO "collector_state"')
    ]
    for database in (path, backup, restored.path):
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    write_minute(restored, 4)
    assert restored.count_observations() == 10
    assert dump(path) == source_dump
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
