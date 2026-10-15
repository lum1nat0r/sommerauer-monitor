"""Durable SQLite storage for measurements, events, and collector metadata."""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    """A database operation failed or the database schema is unsupported."""


class SQLiteStore:
    """Small connection-per-operation SQLite repository with atomic write units."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                self._migrate(connection)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"Could not initialize database: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=3.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 3000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StorageError(
                f"Database schema {version} is newer than supported {SCHEMA_VERSION}"
            )
        if version == 0:
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                    CREATE TABLE profiles (
                        profile_id TEXT NOT NULL,
                        version TEXT NOT NULL,
                        definition_json TEXT NOT NULL,
                        PRIMARY KEY (profile_id, version)
                    );
                    CREATE TABLE signals (
                        signal_id TEXT PRIMARY KEY,
                        unit TEXT NOT NULL,
                        definition_json TEXT NOT NULL
                    );
                    CREATE TABLE requests (
                        request_id TEXT PRIMARY KEY,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        function_code INTEGER NOT NULL,
                        unit_id INTEGER NOT NULL,
                        offset INTEGER NOT NULL,
                        register_count INTEGER NOT NULL,
                        outcome TEXT NOT NULL,
                        error_class TEXT
                    );
                    CREATE TABLE observations (
                        observation_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL REFERENCES requests(request_id),
                        signal_id TEXT NOT NULL REFERENCES signals(signal_id),
                        observed_at TEXT NOT NULL,
                        value INTEGER,
                        unit TEXT NOT NULL,
                        quality TEXT NOT NULL CHECK (quality IN ('ok', 'invalid', 'unavailable')),
                        raw_words_json TEXT NOT NULL,
                        source TEXT NOT NULL,
                        profile_id TEXT NOT NULL,
                        profile_version TEXT NOT NULL,
                        decoder_version TEXT NOT NULL,
                        UNIQUE (request_id, signal_id)
                    );
                    CREATE INDEX observations_signal_time
                        ON observations(signal_id, observed_at, observation_id);
                    CREATE TABLE events (
                        event_id TEXT PRIMARY KEY,
                        occurred_at TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        details_json TEXT NOT NULL
                    );
                    CREATE INDEX events_time ON events(occurred_at, event_id);
                    CREATE TABLE config_versions (
                        version INTEGER PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        config_json TEXT NOT NULL
                    );
                    CREATE TABLE collector_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        state_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    INSERT INTO schema_migrations(version, applied_at)
                        VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                    PRAGMA user_version = 1;
                COMMIT;
                """
            )

    def record_cycle(
        self,
        request: Mapping[str, Any],
        observations: Iterable[Mapping[str, Any]],
    ) -> bool:
        """Persist request and its observations atomically; repeated IDs are no-ops."""
        rows = list(observations)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                inserted = connection.execute(
                    """INSERT OR IGNORE INTO requests
                    (request_id, started_at, completed_at, function_code, unit_id,
                     offset, register_count, outcome, error_class)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request["request_id"], request["started_at"], request.get("completed_at"),
                        request["function_code"], request["unit_id"], request["offset"],
                        request["register_count"], request["outcome"], request.get("error_class"),
                    ),
                ).rowcount
                if not inserted:
                    connection.rollback()
                    return False
                for row in rows:
                    signal_id = row["signal_id"]
                    connection.execute(
                        "INSERT OR IGNORE INTO signals(signal_id, unit, definition_json) VALUES (?, ?, ?)",
                        (signal_id, row["unit"], json.dumps({"signal_id": signal_id}, sort_keys=True)),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO profiles(profile_id, version, definition_json) VALUES (?, ?, ?)",
                        (
                            row["profile_id"], row["profile_version"],
                            json.dumps({"profile_id": row["profile_id"], "version": row["profile_version"]}, sort_keys=True),
                        ),
                    )
                    connection.execute(
                        """INSERT INTO observations
                        (observation_id, request_id, signal_id, observed_at, value, unit, quality,
                         raw_words_json, source, profile_id, profile_version, decoder_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["observation_id"], request["request_id"], signal_id,
                            row["observed_at"], row.get("value"), row["unit"], row["quality"],
                            json.dumps(row["raw_words"], separators=(",", ":")), row["source"],
                            row["profile_id"], row["profile_version"], row["decoder_version"],
                        ),
                    )
                connection.commit()
                return True
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
            raise StorageError(f"Could not store acquisition: {exc}") from exc

    def record_event(
        self, event_id: str, occurred_at: str, kind: str, severity: str,
        message: str, details: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)""",
                    (event_id, occurred_at, kind, severity, message,
                     json.dumps(details or {}, sort_keys=True)),
                )
        except sqlite3.Error as exc:
            raise StorageError(f"Could not store event: {exc}") from exc

    def save_config(self, version: int, config: Mapping[str, Any], created_at: str) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO config_versions VALUES (?, ?, ?)",
                    (version, created_at, json.dumps(config, sort_keys=True)),
                )
        except sqlite3.Error as exc:
            raise StorageError(f"Could not store configuration: {exc}") from exc

    def save_collector_state(self, state: Mapping[str, Any], updated_at: str) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    """INSERT INTO collector_state(singleton, state_json, updated_at)
                    VALUES (1, ?, ?) ON CONFLICT(singleton) DO UPDATE SET
                    state_json=excluded.state_json, updated_at=excluded.updated_at""",
                    (json.dumps(state, sort_keys=True), updated_at),
                )
        except sqlite3.Error as exc:
            raise StorageError(f"Could not store collector state: {exc}") from exc

    def get_collector_state(self) -> dict[str, Any] | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT state_json FROM collector_state WHERE singleton=1"
                ).fetchone()
                return json.loads(row[0]) if row else None
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read collector state: {exc}") from exc

    def history(
        self, signal_id: str, start: str | None = None, end: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be in 1..10000")
        query = "SELECT * FROM observations WHERE signal_id = ?"
        args: list[Any] = [signal_id]
        if start is not None:
            query += " AND observed_at >= ?"
            args.append(start)
        if end is not None:
            query += " AND observed_at < ?"
            args.append(end)
        query += " ORDER BY observed_at, observation_id LIMIT ?"
        args.append(limit)
        try:
            with self._connection() as connection:
                result = []
                for row in connection.execute(query, args):
                    item = dict(row)
                    item["raw_words"] = json.loads(item.pop("raw_words_json"))
                    result.append(item)
                return result
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read history: {exc}") from exc

    def current_signals(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """SELECT o.* FROM observations o
                    JOIN (
                        SELECT signal_id, MAX(observed_at) AS latest
                        FROM observations GROUP BY signal_id
                    ) latest ON latest.signal_id=o.signal_id AND latest.latest=o.observed_at
                    ORDER BY o.signal_id, o.observation_id"""
                )
                result = []
                for row in rows:
                    item = dict(row)
                    item["raw_words"] = json.loads(item.pop("raw_words_json"))
                    result.append(item)
                return result
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read current signals: {exc}") from exc

    def events(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid event pagination")
        try:
            with self._connection() as connection:
                result = []
                for row in connection.execute(
                    "SELECT * FROM events ORDER BY occurred_at DESC, event_id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ):
                    item = dict(row)
                    item["details"] = json.loads(item.pop("details_json"))
                    result.append(item)
                return result
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read events: {exc}") from exc

    def stream_observations(
        self, *, start: str | None = None, end: str | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield original observations in deterministic order without buffering the export."""
        query = "SELECT * FROM observations WHERE 1=1"
        args: list[Any] = []
        if start is not None:
            query += " AND observed_at >= ?"
            args.append(start)
        if end is not None:
            query += " AND observed_at < ?"
            args.append(end)
        query += " ORDER BY observed_at, observation_id"
        try:
            with self._connection() as connection:
                for row in connection.execute(query, args):
                    item = dict(row)
                    item["raw_words"] = json.loads(item.pop("raw_words_json"))
                    yield item
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not export observations: {exc}") from exc

    def database_health(self) -> bool:
        try:
            with self._connection() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def latest_config(self) -> dict[str, Any] | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT config_json FROM config_versions ORDER BY version DESC LIMIT 1"
                ).fetchone()
                return json.loads(row[0]) if row else None
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read configuration: {exc}") from exc

    def next_config_version(self) -> int:
        try:
            with self._connection() as connection:
                return connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM config_versions"
                ).fetchone()[0]
        except sqlite3.Error as exc:
            raise StorageError(f"Could not read configuration version: {exc}") from exc

    def count_observations(
        self, *, signal_id: str | None = None, start: str | None = None, end: str | None = None
    ) -> int:
        query = "SELECT COUNT(*) FROM observations WHERE 1=1"
        args: list[Any] = []
        if signal_id is not None:
            query += " AND signal_id = ?"
            args.append(signal_id)
        if start is not None:
            query += " AND observed_at >= ?"
            args.append(start)
        if end is not None:
            query += " AND observed_at < ?"
            args.append(end)
        try:
            with self._connection() as connection:
                return int(connection.execute(query, args).fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"Could not count observations: {exc}") from exc

    def count_events(self) -> int:
        try:
            with self._connection() as connection:
                return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"Could not count events: {exc}") from exc


    def history_page(
        self, signal_id: str, start: str | None = None, end: str | None = None,
        *, limit: int = 1000, offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10_000 or offset < 0:
            raise ValueError("invalid history pagination")
        query = "SELECT * FROM observations WHERE signal_id = ?"
        args: list[Any] = [signal_id]
        if start is not None:
            query += " AND observed_at >= ?"
            args.append(start)
        if end is not None:
            query += " AND observed_at < ?"
            args.append(end)
        query += " ORDER BY observed_at, observation_id LIMIT ? OFFSET ?"
        args.extend((limit, offset))
        try:
            with self._connection() as connection:
                result = []
                for row in connection.execute(query, args):
                    item = dict(row)
                    item["raw_words"] = json.loads(item.pop("raw_words_json"))
                    result.append(item)
                return result
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read history page: {exc}") from exc

    def disk_usage_bytes(self) -> int:
        try:
            return sum(
                candidate.stat().st_size
                for candidate in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm"))
                if candidate.exists()
            )
        except OSError as exc:
            raise StorageError(f"Could not inspect database storage: {exc}") from exc

    def backup_to(self, destination: str | Path) -> None:
        """Create a consistent standalone backup using SQLite's online backup API."""
        target = Path(destination)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as source, closing(sqlite3.connect(target)) as backup:
                source.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise StorageError(f"Backup integrity check failed: {result}")
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Could not back up database: {exc}") from exc

    @classmethod
    def restore_from(cls, source: str | Path, destination: str | Path) -> SQLiteStore:
        """Restore from a verified backup while preserving a paused collector state."""
        source_path = Path(source)
        target = Path(destination)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(source_path) as backup:
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StorageError("Backup failed SQLite integrity check")
                version = backup.execute("PRAGMA user_version").fetchone()[0]
                if version != SCHEMA_VERSION:
                    raise StorageError(f"Backup schema {version} is not supported")
                state = backup.execute(
                    "SELECT state_json FROM collector_state WHERE singleton=1"
                ).fetchone()
                backup_connection = sqlite3.connect(target)
                try:
                    backup.backup(backup_connection)
                    if state is not None:
                        restored = json.loads(state[0])
                        restored["state"] = "paused"
                        backup_connection.execute(
                            "UPDATE collector_state SET state_json=? WHERE singleton=1",
                            (json.dumps(restored, sort_keys=True),),
                        )
                        backup_connection.commit()
                finally:
                    backup_connection.close()
            return cls(target)
        except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not restore database: {exc}") from exc


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with an explicit UTC offset."""
    return datetime.now(timezone.utc).isoformat()
