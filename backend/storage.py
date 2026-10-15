"""Durable SQLite storage for measurements, events, and collector metadata."""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.registers import CORE_PROFILE


SCHEMA_VERSION = 2

DIAGNOSTIC_ACTIVE_STATES = frozenset({"running", "awaiting_review"})
DIAGNOSTIC_HARD_STATES = frozenset({
    "stopped_transport", "stopped_protocol", "stopped_data", "stopped_storage",
})
DIAGNOSTIC_BLOCKING_STATES = DIAGNOSTIC_HARD_STATES | {"interrupted"}
DIAGNOSTIC_STATES = DIAGNOSTIC_ACTIVE_STATES | DIAGNOSTIC_BLOCKING_STATES | {
    "planned", "completed", "cancelled", "expired",
}


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
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StorageError(
                f"Database schema {version} is newer than supported {SCHEMA_VERSION}"
            )
        if version == 0:
            schema = """
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
                """
            for statement in schema.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations VALUES (1, ?)", (utc_now(),)
            )
        if version < 2:
            statements = (
                """CREATE TABLE diagnostic_runs (
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
                )""",
                """CREATE TABLE diagnostic_requests (
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
                )""",
                """CREATE TABLE control_plans (
                    plan_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (plan_id, revision)
                )""",
                """CREATE UNIQUE INDEX diagnostic_one_active
                    ON diagnostic_runs ((1))
                    WHERE state IN ('running', 'awaiting_review')""",
            )
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations VALUES (2, ?)", (utc_now(),)
            )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _diagnostic_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _diagnostic_timestamp(value: str) -> str:
        if not isinstance(value, str):
            raise StorageError("Diagnosezeit muss ein UTC-Zeitstempel sein")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise StorageError("Ungültiger Diagnosezeitstempel") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise StorageError("Diagnosezeit muss eine Zeitzone enthalten")
        return parsed.astimezone(timezone.utc).isoformat()

    @classmethod
    def _validate_diagnostic_plan(cls, plan: dict) -> str:
        """Prüft den Speichervertrag ohne Katalog-/Settings-Zugriff.

        Der Runner verantwortet Katalogauflösung, Zielbindung und die vollständigen
        fachlichen Stopbedingungen; hier bleiben ihre Texte unverändert erhalten.
        """
        fields = {
            "schema_version", "catalog_sha256", "register_ids", "blocks", "purpose",
            "source", "target", "target_fingerprint", "function_code", "unit_id",
            "deadline_seconds", "request_budget", "min_interval_seconds",
            "max_duration_seconds", "stop_conditions",
        }
        if not isinstance(plan, dict) or set(plan) != fields:
            raise StorageError("Unvollständiger oder unbekannter Diagnoseplanvertrag")
        constants = {
            "schema_version": 1, "function_code": 3, "unit_id": 255,
            "deadline_seconds": 3, "min_interval_seconds": 60,
            "max_duration_seconds": 600,
        }
        for name, value in constants.items():
            if type(plan[name]) is not int or plan[name] != value:
                raise StorageError(f"Ungültiger Diagnoseplanwert: {name}")
        for name in ("catalog_sha256", "target_fingerprint"):
            value = plan[name]
            if (not isinstance(value, str) or len(value) != 64
                    or any(character not in "0123456789abcdef" for character in value)):
                raise StorageError(f"Ungültiger Diagnosehash: {name}")
        if not isinstance(plan["purpose"], str) or not plan["purpose"].strip():
            raise StorageError("Diagnosezweck fehlt")
        if plan["source"] not in ("device", "simulator"):
            raise StorageError("Ungültige Diagnosequelle")
        target = plan["target"]
        if (not isinstance(target, dict) or set(target) != {"host", "port"}
                or not isinstance(target["host"], str) or not target["host"].strip()
                or type(target["port"]) is not int or not 1 <= target["port"] <= 65535):
            raise StorageError("Ungültiger privater Zielsnapshot")
        blocks = plan["blocks"]
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 3:
            raise StorageError("Diagnose benötigt ein bis drei Blöcke")
        covered: set[int] = set()
        for block in blocks:
            if (not isinstance(block, dict) or set(block) != {"offset", "count"}
                    or type(block["offset"]) is not int
                    or type(block["count"]) is not int
                    or not 0 <= block["offset"] <= 65535
                    or not 1 <= block["count"] <= 2
                    or block["offset"] + block["count"] > 65536):
                raise StorageError("Ungültiger Diagnoseblock")
            words = set(range(block["offset"], block["offset"] + block["count"]))
            if covered & words:
                raise StorageError("Überlappende Diagnoseblöcke")
            covered.update(words)
        ids = plan["register_ids"]
        if (not isinstance(ids, list) or not ids
                or any(not isinstance(identifier, str) for identifier in ids)
                or len(set(ids)) != len(ids)):
            raise StorageError("Ungültige Diagnoseauswahl")
        selected: set[int] = set()
        for identifier in ids:
            prefix, separator, offset = identifier.partition(":")
            if (prefix != "register" or not separator or not offset.isascii()
                    or not offset.isdecimal() or str(int(offset)) != offset
                    or int(offset) not in covered):
                raise StorageError("Diagnoseauswahl passt nicht zur Blockliste")
            selected.add(int(offset))
        if any(not selected.intersection(range(block["offset"], block["offset"] + block["count"]))
               for block in blocks):
            raise StorageError("Diagnoseblock ohne ausgewähltes Register")
        if type(plan["request_budget"]) is not int or plan["request_budget"] != len(blocks):
            raise StorageError("Diagnosebudget muss der Blockanzahl entsprechen")
        conditions = plan["stop_conditions"]
        if (not isinstance(conditions, list) or not conditions
                or any(not isinstance(condition, str) or not condition.strip()
                       for condition in conditions)):
            raise StorageError("Diagnose-Stopbedingungen fehlen")
        return cls._diagnostic_json(plan)

    @staticmethod
    def _diagnostic_run_row(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM diagnostic_runs WHERE run_id = ?", (run_id,),
        ).fetchone()
        if row is None:
            raise StorageError("Diagnoselauf nicht gefunden")
        return row

    @staticmethod
    def _diagnostic_blocker(
        connection: sqlite3.Connection, excluding: str | None = None,
    ) -> str | None:
        row = connection.execute(
            """SELECT run_id FROM diagnostic_runs
            WHERE (state IN ('running', 'awaiting_review')
                OR (state IN ('interrupted', 'stopped_transport', 'stopped_protocol',
                             'stopped_data', 'stopped_storage') AND acknowledged_at IS NULL))
                AND (? IS NULL OR run_id != ?)
            ORDER BY created_at, run_id LIMIT 1""", (excluding, excluding),
        ).fetchone()
        return row["run_id"] if row else None

    @staticmethod
    def _diagnostic_document(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        """Privates SQLite-Dokument, ausdrücklich keine öffentliche API-Projektion."""
        document = dict(row)
        document["plan"] = json.loads(document.pop("plan_json"))
        requests = connection.execute(
            "SELECT * FROM diagnostic_requests WHERE run_id = ? ORDER BY step_index",
            (row["run_id"],),
        ).fetchall()
        document["requests"] = []
        for request in requests:
            item = dict(request)
            for field in ("raw_words", "decoded", "review"):
                encoded = item.pop(f"{field}_json")
                item[field] = json.loads(encoded) if encoded is not None else None
            document["requests"].append(item)
        return document

    def create_diagnostic_run(self, plan: dict) -> dict:
        """Speichert einen unveränderlichen privaten Plan ohne Gerätezugriff."""
        try:
            encoded = self._validate_diagnostic_plan(plan)
            now, run_id = utc_now(), str(uuid4())
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if self._diagnostic_blocker(connection) is not None:
                    raise StorageError("Ein Diagnoselauf sperrt neue Planung")
                connection.execute(
                    """INSERT INTO diagnostic_runs
                    (run_id, created_at, updated_at, plan_json, state, requests_reserved)
                    VALUES (?, ?, ?, ?, 'planned', 0)""", (run_id, now, now, encoded),
                )
                return self._diagnostic_document(
                    connection, self._diagnostic_run_row(connection, run_id),
                )
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnoseplan konnte nicht gespeichert werden: {exc}") from exc

    def get_diagnostic_run(self, run_id: str) -> dict | None:
        try:
            with self._connection() as connection:
                connection.execute("BEGIN")
                row = connection.execute(
                    "SELECT * FROM diagnostic_runs WHERE run_id = ?", (run_id,),
                ).fetchone()
                return self._diagnostic_document(connection, row) if row else None
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnoselauf konnte nicht gelesen werden: {exc}") from exc

    def list_diagnostic_runs(self, limit: int, offset: int) -> list[dict]:
        if type(limit) is not int or limit < 1 or type(offset) is not int or offset < 0:
            raise StorageError("Ungültige Diagnosepagination")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN")
                rows = connection.execute(
                    """SELECT * FROM diagnostic_runs ORDER BY created_at DESC, run_id DESC
                    LIMIT ? OFFSET ?""", (limit, offset),
                ).fetchall()
                return [self._diagnostic_document(connection, row) for row in rows]
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnoseläufe konnten nicht gelesen werden: {exc}") from exc

    def reserve_diagnostic_request(self, run_id: str, step_index: int, started_at: str) -> None:
        try:
            started_at = self._diagnostic_timestamp(started_at)
            if type(step_index) is not int or step_index < 0:
                raise StorageError("Ungültiger Diagnoseschritt")
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._diagnostic_run_row(connection, run_id)
                plan = json.loads(run["plan_json"])
                if run["state"] not in ("planned", "running"):
                    raise StorageError("Diagnoselauf ist nicht ausführbar")
                if self._diagnostic_blocker(connection, excluding=run_id) is not None:
                    raise StorageError("Ein anderer Diagnoselauf sperrt den Zugriff")
                if (step_index != run["requests_reserved"]
                        or step_index >= plan["request_budget"]):
                    raise StorageError("Diagnoseschritt bereits verbraucht oder Budget erschöpft")
                if step_index:
                    previous = connection.execute(
                        """SELECT review_json FROM diagnostic_requests
                        WHERE run_id = ? AND step_index = ?""", (run_id, step_index - 1),
                    ).fetchone()
                    if (previous is None or previous["review_json"] is None
                            or json.loads(previous["review_json"])["verdict"] != "continue"):
                        raise StorageError("Vorherige Diagnoseantwort ist nicht freigegeben")
                now = utc_now()
                connection.execute(
                    """INSERT INTO diagnostic_requests
                    (run_id, step_index, outcome, started_at, received_bytes)
                    VALUES (?, ?, 'reserved', ?, 0)""", (run_id, step_index, started_at),
                )
                connection.execute(
                    """UPDATE diagnostic_runs SET requests_reserved = requests_reserved + 1,
                    state = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                    WHERE run_id = ?""", (now, now, run_id),
                )
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnoseanfrage konnte nicht reserviert werden: {exc}") from exc

    def finish_diagnostic_request(
        self, run_id: str, step_index: int, result: dict, state: str,
    ) -> None:
        try:
            required = {"outcome", "raw_words", "decoded", "error_class", "received_bytes"}
            if (not isinstance(result, dict) or not required <= set(result)
                    or set(result) - required - {"completed_at"}
                    or type(step_index) is not int or step_index < 0):
                raise StorageError("Ungültiges Diagnoseergebnis")
            if state not in DIAGNOSTIC_HARD_STATES | {"awaiting_review", "cancelled", "expired"}:
                raise StorageError("Ungültiger Diagnoseabschlusszustand")
            outcome = result["outcome"]
            if not isinstance(outcome, str) or not outcome.strip() or outcome == "reserved":
                raise StorageError("Ungültiges Diagnoseergebnis")
            error = result["error_class"]
            if error is not None and (not isinstance(error, str) or not error.strip()):
                raise StorageError("Ungültige Diagnosefehlerklasse")
            if type(result["received_bytes"]) is not int or result["received_bytes"] < 0:
                raise StorageError("Ungültige empfangene Byteanzahl")
            words = result["raw_words"]
            if words is not None and (
                not isinstance(words, list)
                or any(type(word) is not int or not 0 <= word <= 65535 for word in words)
            ):
                raise StorageError("Ungültige Diagnoserohworte")
            successful = outcome in ("ok", "success")
            if state == "awaiting_review" and (
                not successful or error is not None or words is None
            ):
                raise StorageError("Fehlerhafte Antwort darf nicht zur Bewertung freigegeben werden")
            if state in DIAGNOSTIC_HARD_STATES and (error is None or successful):
                raise StorageError("Harter Diagnosefehler benötigt ein Fehlerergebnis")
            if error is not None and (successful or state not in DIAGNOSTIC_HARD_STATES):
                raise StorageError("Diagnosefehler benötigt einen harten Stopp")
            if error is not None and result["decoded"] is not None:
                raise StorageError("Fehlerhafte Interpretation darf nicht als dekodiert gelten")
            raw_json = self._diagnostic_json(words) if words is not None else None
            decoded_json = (
                self._diagnostic_json(result["decoded"]) if result["decoded"] is not None else None
            )
            completed_at = self._diagnostic_timestamp(result.get("completed_at", utc_now()))
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._diagnostic_run_row(connection, run_id)
                request = connection.execute(
                    "SELECT * FROM diagnostic_requests WHERE run_id = ? AND step_index = ?",
                    (run_id, step_index),
                ).fetchone()
                if (request is None or request["outcome"] != "reserved"
                        or request["completed_at"] is not None
                        or step_index != run["requests_reserved"] - 1):
                    raise StorageError("Diagnoseantwort fehlt oder wurde bereits gespeichert")
                block = json.loads(run["plan_json"])["blocks"][step_index]
                if result["decoded"] is not None and not any(
                    block["offset"] == core.offset and block["count"] == core.count
                    for core in CORE_PROFILE
                ):
                    raise StorageError("Dekodierung ist ausschließlich für bestätigte Kernblöcke erlaubt")
                if successful and (words is None or len(words) != block["count"]):
                    raise StorageError("Erfolgreiche Diagnoseantwort passt nicht zum gespeicherten Block")
                if run["state"] not in (
                    DIAGNOSTIC_HARD_STATES | {"running", "cancelled", "expired", "interrupted"}
                ):
                    raise StorageError("Diagnoselauf erlaubt keinen Antwortabschluss")
                final_state = state
                if run["state"] in DIAGNOSTIC_BLOCKING_STATES:
                    final_state = run["state"]
                elif run["state"] in {"cancelled", "expired"} and state not in DIAGNOSTIC_HARD_STATES:
                    final_state = run["state"]
                if run["state"] == "interrupted" and state in DIAGNOSTIC_HARD_STATES:
                    final_state = state
                connection.execute(
                    """UPDATE diagnostic_requests SET outcome = ?, completed_at = ?,
                    raw_words_json = ?, decoded_json = ?, error_class = ?, received_bytes = ?
                    WHERE run_id = ? AND step_index = ?""",
                    (outcome, completed_at, raw_json, decoded_json, error,
                     result["received_bytes"], run_id, step_index),
                )
                terminal = final_state != "awaiting_review"
                reason = run["stop_reason"]
                if final_state in DIAGNOSTIC_HARD_STATES and run["state"] not in DIAGNOSTIC_HARD_STATES:
                    reason = error
                elif terminal and reason is None:
                    reason = final_state
                connection.execute(
                    """UPDATE diagnostic_runs SET state = ?, updated_at = ?, ended_at = ?,
                    stop_reason = ?, acknowledged_at = CASE WHEN ? THEN NULL ELSE acknowledged_at END,
                    resolution_note = CASE WHEN ? THEN NULL ELSE resolution_note END
                    WHERE run_id = ?""",
                    (final_state, utc_now(), (run["ended_at"] or completed_at) if terminal else None,
                     reason, state in DIAGNOSTIC_HARD_STATES, state in DIAGNOSTIC_HARD_STATES, run_id),
                )
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnoseantwort konnte nicht gespeichert werden: {exc}") from exc

    def review_diagnostic_request(
        self, run_id: str, step_index: int, review: dict, state: str,
    ) -> None:
        try:
            if (not isinstance(review, dict) or set(review) != {"verdict", "observation"}
                    or review["verdict"] not in ("continue", "finish", "anomaly")
                    or (review["observation"] is not None
                        and not isinstance(review["observation"], str))
                    or type(step_index) is not int or step_index < 0):
                raise StorageError("Ungültige Diagnosebewertung")
            encoded = self._diagnostic_json(review)
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._diagnostic_run_row(connection, run_id)
                if run["state"] != "awaiting_review" or step_index != run["requests_reserved"] - 1:
                    raise StorageError("Diagnoselauf wartet nicht auf diese Bewertung")
                request = connection.execute(
                    "SELECT * FROM diagnostic_requests WHERE run_id = ? AND step_index = ?",
                    (run_id, step_index),
                ).fetchone()
                if (request is None or request["completed_at"] is None
                        or request["review_json"] is not None or request["error_class"] is not None):
                    raise StorageError("Diagnoseantwort kann nicht bewertet werden")
                last = run["requests_reserved"] == json.loads(run["plan_json"])["request_budget"]
                expected = {
                    "continue": "completed" if last else "running",
                    "finish": "cancelled", "anomaly": "stopped_data",
                }[review["verdict"]]
                if state != expected:
                    raise StorageError("Bewertung und Diagnosezustand widersprechen sich")
                now = utc_now()
                connection.execute(
                    """UPDATE diagnostic_requests SET review_json = ?
                    WHERE run_id = ? AND step_index = ?""", (encoded, run_id, step_index),
                )
                connection.execute(
                    """UPDATE diagnostic_runs SET state = ?, updated_at = ?, ended_at = ?,
                    stop_reason = ? WHERE run_id = ?""",
                    (state, now, None if state == "running" else now,
                     None if state == "running" else review["verdict"], run_id),
                )
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
            raise StorageError(f"Diagnosebewertung konnte nicht gespeichert werden: {exc}") from exc

    def set_diagnostic_run_state(self, run_id: str, state: str, reason: str | None) -> None:
        if (not isinstance(state, str) or state not in DIAGNOSTIC_STATES
                or (reason is not None and (not isinstance(reason, str) or not reason.strip()))):
            raise StorageError("Ungültiger Diagnosezustand oder Stoppgrund")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._diagnostic_run_row(connection, run_id)
                current = run["state"]
                if current in DIAGNOSTIC_HARD_STATES and state in {"cancelled", "expired"}:
                    return
                if state == current:
                    return
                if state == "running":
                    if current != "planned":
                        raise StorageError("Diagnoselauf darf nicht erneut gestartet werden")
                    if self._diagnostic_blocker(connection, excluding=run_id) is not None:
                        raise StorageError("Ein anderer Diagnoselauf sperrt den Start")
                elif state in DIAGNOSTIC_HARD_STATES:
                    if current not in {"planned", "running", "awaiting_review", "cancelled", "expired"}:
                        raise StorageError("Diagnoselauf ist bereits terminal")
                elif state in {"cancelled", "expired"}:
                    if current not in {"planned", "running", "awaiting_review"}:
                        raise StorageError("Diagnoselauf ist bereits terminal")
                elif state == "interrupted":
                    if current not in DIAGNOSTIC_ACTIVE_STATES:
                        raise StorageError("Nur aktive Diagnosen können unterbrochen werden")
                else:
                    raise StorageError("Dieser Diagnoseübergang erfordert Antwort oder Bewertung")
                now = utc_now()
                connection.execute(
                    """UPDATE diagnostic_runs SET state = ?, updated_at = ?,
                    started_at = CASE WHEN ? = 'running' THEN COALESCE(started_at, ?) ELSE started_at END,
                    ended_at = ?, stop_reason = ? WHERE run_id = ?""",
                    (state, now, state, now, None if state == "running" else now,
                     None if state == "running" else (reason or state), run_id),
                )
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Diagnosezustand konnte nicht gespeichert werden: {exc}") from exc

    def acknowledge_diagnostic_run(self, run_id: str, resolution: str) -> None:
        if not isinstance(resolution, str) or not resolution.strip():
            raise StorageError("Quittierung benötigt einen nichtleeren Ursachentext")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._diagnostic_run_row(connection, run_id)
                if run["state"] not in DIAGNOSTIC_BLOCKING_STATES or run["acknowledged_at"] is not None:
                    raise StorageError("Diagnoselauf kann nicht quittiert werden")
                now = utc_now()
                connection.execute(
                    """UPDATE diagnostic_runs SET acknowledged_at = ?, resolution_note = ?,
                    updated_at = ? WHERE run_id = ?""", (now, resolution, now, run_id),
                )
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Diagnosequittierung konnte nicht gespeichert werden: {exc}") from exc

    def diagnostic_access_blocker(self) -> str | None:
        try:
            with self._connection() as connection:
                return self._diagnostic_blocker(connection)
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Diagnosesperre konnte nicht gelesen werden: {exc}") from exc

    def has_diagnostic_requests(self) -> bool:
        try:
            with self._connection() as connection:
                return connection.execute("SELECT 1 FROM diagnostic_requests LIMIT 1").fetchone() is not None
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Diagnosehistorie konnte nicht gelesen werden: {exc}") from exc

    def interrupt_active_diagnostic_runs(self) -> None:
        """Nur der Laufzeitbesitzer unter OS-Sperre darf die Wiederherstellung aufrufen."""
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                now = utc_now()
                connection.execute(
                    """UPDATE diagnostic_runs SET state = 'interrupted', updated_at = ?,
                    ended_at = ?, stop_reason = 'interrupted', acknowledged_at = NULL,
                    resolution_note = NULL WHERE state IN ('running', 'awaiting_review')""",
                    (now, now),
                )
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Aktive Diagnosen konnten nicht unterbrochen werden: {exc}") from exc

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
        """Restore only into a new offline target; never modify the source backup."""
        source_path = Path(source)
        target = Path(destination)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(
                source_path.resolve().as_uri() + "?mode=ro", uri=True
            )) as backup:
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StorageError("Backup failed SQLite integrity check")
                version = backup.execute("PRAGMA user_version").fetchone()[0]
                if version not in (1, SCHEMA_VERSION):
                    raise StorageError(f"Backup schema {version} is not supported")
                state = backup.execute(
                    "SELECT state_json FROM collector_state WHERE singleton=1"
                ).fetchone()
                # Exclusive creation forbids restoring over a live or existing volume.
                with target.open("xb"):
                    pass
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
            store = cls(target)
            store.interrupt_active_diagnostic_runs()
            return store
        except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not restore database: {exc}") from exc


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with an explicit UTC offset."""
    return datetime.now(timezone.utc).isoformat()
