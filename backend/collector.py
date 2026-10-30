"""Single-owner, bounded collector for explicitly selected register blocks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from backend.modbus import (
    ConnectionError as ModbusConnectionError,
    IncompleteResponseError,
    ModbusError,
    ModbusExceptionError,
    ModbusTcpClient,
    ProtocolError,
)
from backend.registers import (
    CORE_PROFILE,
    PROFILE_ID,
    READ_PROFILE,
    REGISTER_DEFINITIONS,
    DecodeError,
    DecodedSignal,
    SIGNAL_DEFINITIONS,
    decode_register_block,
    validate_operating_counter_progression,
)
from backend.storage import SQLiteStore, StorageError

MIN_BLOCK_INTERVAL_SECONDS = 60.0
EXTENDED_BLOCK_INTERVAL_SECONDS = 300.0



class CollectorOwnershipError(RuntimeError):
    """Another process currently owns this deployment's collector lock."""


class CollectorStopped(RuntimeError):
    """The collector ended in a non-running state."""


class _ProcessLock:
    """OS-backed exclusive lock, held for the collector's complete lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                if self._file.read(1) == b"":
                    self._file.write(b"0")
                    self._file.flush()
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._file.close()
            self._file = None
            raise CollectorOwnershipError("collector lock is held by another process") from exc
        except BaseException:
            self._file.close()
            self._file = None
            raise

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


class Collector:
    """Sequential collector; browser/API requests never initiate Modbus reads."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        store: SQLiteStore,
        data_dir: Path,
        client: Any | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
        wait: Callable[[threading.Event, float], bool] | None = None,
        now: Callable[[], datetime] | None = None,
        max_duration_seconds: float | None = None,
        max_requests: int | None = None,
        retry_on_transport_error: bool = True,
    ) -> None:
        if max_duration_seconds is not None and max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        if max_requests is not None and max_requests < 1:
            raise ValueError("max_requests must be at least one")
        self.store = store
        self.client = client or ModbusTcpClient(host, port)
        self.monotonic = monotonic
        self.wait = wait or (lambda event, seconds: event.wait(seconds))
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.max_duration_seconds = max_duration_seconds
        self.max_requests = max_requests
        self.retry_on_transport_error = retry_on_transport_error
        self._lock = _ProcessLock(data_dir / "collector.lock")
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._request_count = 0
        self._last_completed: dict[int, float] = {}
        self._last_completed_at: dict[int, datetime] = {}
        self._last_counter: tuple[int, datetime] | None = None
        self._endpoint_id = self._configuration_id(host, port)
        self._next_offset = READ_PROFILE[0].offset
        self._retry_block_offset = READ_PROFILE[0].offset
        self._reconnect_attempts = 0
        self._retry_at: datetime | None = None
        self._last_action: str | None = None
        self._request_in_flight = False
        self.state = "paused"
        self.error: str | None = None
        self._has_saved_state = False
        self.blocked_signals: set[str] = set()
        self._signal_errors: dict[str, str] = {}
        self._logging_config: dict[str, Any] = {"revision": 0, "entries": []}
        self._restore_state()
        try:
            self._logging_config = self.store.get_logging_config()
        except StorageError:
            self.state = "stopped_storage"
            self.error = "Speicherzugriff fehlgeschlagen; Erfassung angehalten."
        if self.state == "paused":
            self._paused.set()

    @staticmethod
    def _configuration_id(host: str, port: int) -> str:
        import hashlib

        return hashlib.sha256(f"{host.casefold()}:{port}:255:{PROFILE_ID}".encode()).hexdigest()

    def status(self) -> dict[str, Any]:
        reasons = {
            "reconnect_wait": "Verbindungsfehler; Abfragen laufen im regulären Intervall weiter",
            "stopped_transport": "Transportfehler; Erfassung angehalten",
            "stopped_protocol": "Protokollfehler; Erfassung angehalten",
            "stopped_data": "Datenfehler; Erfassung angehalten",
            "stopped_storage": "Speicher- oder Zustandsfehler; Erfassung angehalten",
            "paused": "Erfassung pausiert",
        }
        if self.state == "stopped_transport" and not self.retry_on_transport_error:
            reasons["stopped_transport"] = "Endlicher Lauf wegen Transportfehler beendet"
        if self.state == "stopped_transport" and self._read_to_clear(
            self._block_by_offset(self._retry_block_offset)
        ):
            reasons["stopped_transport"] = "Read-to-clear-Auslesung ungewiss; automatische Wiederholung gesperrt"
        next_action_at = self._retry_at
        if self.state == "reconnect_wait":
            selected = self._selected_signals()
            due = min(
                (self._due_at(block) for block in READ_PROFILE
                 if selected.intersection(block.signal_ids)),
                default=None,
            )
            next_action_at = (
                self.now() + timedelta(seconds=max(0.0, due - self.monotonic()))
                if due is not None else None
            )
        reason = reasons.get(self.state) if self.error else None
        if self.state == "running" and self.blocked_signals:
            reason = f"{len(self.blocked_signals)} Werte ausgesetzt; Details an den Kacheln"
        return {
            "state": self.state,
            "reason": reason,
            "reconnect_attempts": self._reconnect_attempts,
            "next_action_at": next_action_at.isoformat() if next_action_at else None,
            "next_action": self._last_action,
            "profile_id": PROFILE_ID,
            "blocked_signal_count": len(self.blocked_signals),
        }

    def logging_status(self, saved_revision: int | None = None) -> dict[str, Any]:
        """Aktiven Zyklus-Snapshot getrennt vom gespeicherten Entwurf melden."""
        active = self._logging_config
        if saved_revision is None:
            saved_revision = self.store.get_logging_config()["revision"]
        return {
            "active_revision": active["revision"],
            "active_entries": active["entries"],
            "apply_status": "aktiv" if saved_revision == active["revision"] else "ausstehend",
        }

    def _selected_signals(self) -> set[str]:
        return {
            entry["signal_id"] for entry in self._logging_config["entries"]
            if entry["record"] and entry["eligible"] and entry["signal_id"] is not None
            and entry["signal_id"] not in self.blocked_signals
        }

    def _advance_block(self, block) -> None:
        self._next_offset = READ_PROFILE[
            (next(i for i, candidate in enumerate(READ_PROFILE) if candidate.offset == block.offset) + 1)
            % len(READ_PROFILE)
        ].offset

    @staticmethod
    def _read_to_clear(block) -> bool:
        return any(
            REGISTER_DEFINITIONS[f"{offset:04X}"]["read_to_clear"]
            for offset in range(block.offset, block.offset + block.count)
        )

    def _restore_state(self) -> None:

        try:
            saved = self.store.get_collector_state()
        except StorageError:
            self.state = "stopped_storage"
            self.error = "Gespeicherter Erfassungszustand konnte nicht geladen werden."
            self._last_action = "Inspect storage; no automatic reads"
            return
        self._has_saved_state = saved is not None
        if saved is None:
            self._last_action = "Start collection"
            return
        try:
            blocked = saved.get("blocked_signals", [])
            if (
                not isinstance(blocked, list)
                or any(not isinstance(signal_id, str) or signal_id not in SIGNAL_DEFINITIONS for signal_id in blocked)
                or len(blocked) != len(set(blocked))
            ):
                raise ValueError("persisted blocked signal IDs are invalid")
            # Wertfehler sperren nicht mehr; alte Sperren daraus beim Start verwerfen.
            self.blocked_signals = set(blocked) & {
                row["signal_id"] for row in self.store.current_signals()
                if str(row.get("error_code") or "").startswith("modbus_exception")
            }
            if saved["configuration_id"] != self._endpoint_id or saved["profile_id"] != PROFILE_ID:
                self.error = "Saved state belongs to a different target or profile"
                self._last_action = "Review configuration and acknowledge"
                return
            self.state = saved["state"]
            self.error = saved.get("error")
            self._request_count = int(saved.get("request_count", 0))
            self._reconnect_attempts = int(saved.get("reconnect_attempts", 0))
            self._next_offset = int(saved.get("next_offset", READ_PROFILE[0].offset))
            self._retry_block_offset = int(saved.get("retry_block_offset", READ_PROFILE[0].offset))
            valid_offsets = {block.offset for block in READ_PROFILE}
            if (
                self._reconnect_attempts < 0
                or self._next_offset not in valid_offsets
                or self._retry_block_offset not in valid_offsets
            ):
                raise ValueError("persisted recovery counters or block offsets are invalid")
            if not isinstance(saved.get("last_completed_at", {}), dict):
                raise ValueError("persisted completion timestamps are invalid")
            for raw_offset, raw_completed in saved.get("last_completed_at", {}).items():
                offset = int(raw_offset)
                if offset not in valid_offsets:
                    raise ValueError("persisted completion offset is invalid")
                completed = datetime.fromisoformat(raw_completed)
                elapsed = max(0.0, (self.now() - completed).total_seconds())
                block = self._block_by_offset(offset)
                interval = self._block_interval(block)
                self._last_completed[offset] = self.monotonic() - min(elapsed, interval)
                self._last_completed_at[offset] = completed
            if not saved.get("request_in_flight", False):
                for _ in READ_PROFILE:
                    candidate = self._block_by_offset(self._next_offset)
                    if not set(candidate.signal_ids).issubset(self.blocked_signals):
                        break
                    self._advance_block(candidate)
            self._last_action = saved.get("next_action")
            block = self._block_by_offset(self._retry_block_offset)
            in_flight = saved.get("request_in_flight", False)
            pending_retry = (
                self.state == "reconnect_wait" or saved.get("retry_at") is not None
                or saved.get("retry_delay_seconds") is not None
            )
            if (
                self.state in {"running", "reconnect_wait", "paused", "stopped_transport"}
                and self._read_to_clear(block) and (in_flight or pending_retry)
            ):
                self.state = "stopped_transport"
                self.error = "Ungewisser Ausgang einer Read-to-clear-Auslesung; keine automatische Wiederholung"
                self._last_action = "Protokollauslesung prüfen und ausdrücklich bestätigen"
            elif (
                self.state == "stopped_transport"
                and self.retry_on_transport_error
                and self.max_requests is None and self.max_duration_seconds is None
                and saved.get("max_requests") is None and saved.get("max_duration_seconds") is None
                and not self._read_to_clear(block)
            ):
                # Alte Transportstopps ohne endlichen Lauf dürfen den Dauerbetrieb nicht sperren.
                self.state = "reconnect_wait"
                pending_retry = True
            if in_flight or pending_retry:
                self._last_completed[block.offset] = self.monotonic()
                self._last_completed_at[block.offset] = self.now()
                if self.state in {"running", "reconnect_wait", "paused"}:
                    self._retry_at = self.now() + timedelta(seconds=self._block_interval(block))
                    if in_flight:
                        self.error = "Ausgang der letzten Anfrage nach Neustart ungewiss."
                    if self.state != "paused":
                        self.state = "reconnect_wait"
                    self._last_action = "Nächste Abfrage im regulären Intervall"
            if self.state not in {
                "running", "reconnect_wait", "paused", "stopped_transport", "stopped_protocol",
                "stopped_data", "stopped_storage", "completed",
            }:
                raise ValueError("unknown persisted collector state")
        except (KeyError, TypeError, ValueError, OverflowError):
            self.state = "stopped_storage"
            self.error = "Persisted collector state is invalid"
            self._retry_at = None
            self._last_action = "Inspect persisted state; no automatic reads"
        if self.state not in {"running", "reconnect_wait"}:
            self._paused.set()

    def acknowledge_and_start(self) -> None:
        if self.state not in {
            "paused", "stopped_transport", "stopped_protocol", "stopped_data",
            "stopped_storage", "completed",
        }:
            raise CollectorStopped(f"cannot acknowledge collector in state {self.state}")
        self.error = None
        self.blocked_signals.clear()
        self._signal_errors.clear()
        self._last_counter = None
        self._reconnect_attempts = 0
        self._retry_at = None
        self.state = "paused"
        self._last_action = "Start collection"
        self._has_saved_state = False
        self._persist_state()
        self._paused.clear()
        if self._thread is None or not self._thread.is_alive():
            self.start()

    def start(self) -> None:
        """Acquire ownership before creating the background worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        if self._has_saved_state and self.state == "paused":
            return
        if self.state.startswith("stopped_") or self.state in {"stopped_protocol", "completed"}:
            return
        self._lock.acquire()
        self._stop.clear()
        self._wake.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self.run, name="sommerauer-collector", daemon=True)
        self._thread.start()

    def run(self) -> None:
        """Run until stopped, paused, failed, or a configured finite limit is reached."""
        try:
            if self._thread is None:
                self._lock.acquire()
            if not self._has_saved_state:
                self._paused.clear()
            if self.state != "reconnect_wait":
                self.state = "running"
            self._started_at = self.monotonic()
            self._persist_state()
            while not self._stop.is_set():
                if self._paused.is_set():
                    self.state = "paused"
                    self._last_action = "Resume collection"
                    self._persist_state()
                    if self.wait(self._stop, 0.1):
                        break
                    continue
                if self._limit_reached():
                    self.state = "completed"
                    self._last_action = "Finite collection limit reached"
                    self._persist_state()
                    break
                block = None
                # Langsame oder fehlgeschlagene Blöcke verdrängen keine anderen fälligen Werte.
                for _ in range(len(READ_PROFILE)):
                    if self._next_offset == READ_PROFILE[0].offset or not self._selected_signals():
                        saved_config = self.store.get_logging_config()
                        if saved_config["revision"] != self._logging_config["revision"]:
                            self._logging_config = saved_config
                            self._next_offset = READ_PROFILE[0].offset
                    selected = self._selected_signals()
                    if not selected:
                        break
                    candidate = self._block_by_offset(self._next_offset)
                    if selected.intersection(candidate.signal_ids) and self._due_at(candidate) <= self.monotonic():
                        block = candidate
                        break
                    self._advance_block(candidate)
                if block is None:
                    if not selected:
                        self._last_action = (
                            "Werte ausgesetzt; Details an den Kacheln"
                            if self.blocked_signals else "Keine freigegebenen Signale ausgewählt"
                        )
                        self.wait(self._stop, 0.25)
                    else:
                        due = min(
                            self._due_at(candidate) for candidate in READ_PROFILE
                            if selected.intersection(candidate.signal_ids)
                        )
                        if not self._wait_until(due):
                            break
                    continue
                if self._stop.is_set() or self._paused.is_set() or self._limit_reached():
                    continue
                self._read_one(block)
            if self.state == "running":
                self.state = "paused"
                self._last_action = "Collection paused"
                self._persist_state()
        except CollectorOwnershipError:
            self.state = "ownership_error"
            self.error = "collector lock is held by another process"
            raise
        except StorageError:
            self.state = "stopped_storage"
            self.error = "Speicherzugriff fehlgeschlagen; Erfassung angehalten."
            self._persist_state_best_effort()
        finally:
            self._lock.release()

    def pause(self) -> None:
        """Pause future reads; an in-flight read may finish by its transport deadline."""
        self._paused.set()
        self._wake.set()
        if self.state in {"running", "reconnect_wait"}:
            self.state = "paused"
            self._last_action = "Collection paused"
            self._persist_state()

    def resume(self) -> None:
        if self.state not in {"paused"}:
            raise CollectorStopped(f"cannot resume collector in state {self.state}")
        self._paused.clear()
        self._wake.clear()
        self.state = "reconnect_wait" if self._retry_at is not None else "running"
        self._last_action = (
            "Nächste Abfrage im regulären Intervall"
            if self.state == "reconnect_wait" else "Resume collection"
        )
        self._has_saved_state = False
        self._persist_state()
        if self._thread is None or not self._thread.is_alive():
            self.start()

    def stop(self, timeout: float | None = 4.0) -> None:
        """Prevent new reads, allow an in-flight request to finish, then join the worker."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise TimeoutError("collector did not stop before the join timeout")
            self._thread = None
        if self.state not in {
            "stopped_storage", "stopped_protocol", "stopped_data",
            "stopped_transport", "completed", "reconnect_wait",
        }:
            self.state = "paused"
            self._last_action = "Collection paused"
            self._persist_state()

    def _limit_reached(self) -> bool:
        return (
            (self.max_requests is not None and self._request_count >= self.max_requests)
            or (
                self.max_duration_seconds is not None
                and self._started_at is not None
                and self.monotonic() - self._started_at >= self.max_duration_seconds
            )
        )

    @staticmethod
    def _block_by_offset(offset: int):
        for block in READ_PROFILE:
            if block.offset == offset:
                return block
        raise StorageError("Persisted collector block is outside the explicit read profile")

    @staticmethod
    def _block_interval(block) -> float:
        return (
            MIN_BLOCK_INTERVAL_SECONDS
            if block in CORE_PROFILE else EXTENDED_BLOCK_INTERVAL_SECONDS
        )

    def _due_at(self, block) -> float:
        due = self._started_at if self._started_at is not None else self.monotonic()
        previous = self._last_completed.get(block.offset)
        if previous is not None:
            due = max(due, previous + self._block_interval(block))
        return due

    def _wait_until(self, due: float) -> bool:
        while (
            not self._stop.is_set()
            and not self._paused.is_set()
            and self.monotonic() < due
        ):
            if self.wait(self._wake, due - self.monotonic()):
                break
        return not self._stop.is_set()

    def _read_one(self, block) -> None:
        if self.state == "reconnect_wait":
            self._reconnect_attempts += 1
        self._retry_at = None
        started = self.now()
        self._request_count += 1
        self._retry_block_offset = block.offset
        self.state = "running"
        self._request_in_flight = True
        self._last_action = f"Read register block at offset {block.offset}"
        # Reserve every outbound attempt durably before touching the socket.
        self._persist_state()
        request_id = str(uuid4())
        request: dict[str, Any] = {
            "request_id": request_id,
            "started_at": started.isoformat(),
            "completed_at": None,
            "function_code": 3,
            "unit_id": 255,
            "offset": block.offset,
            "register_count": block.count,
            "outcome": "error",
            "error_class": None,
        }
        raw_words: tuple[int, ...] = ()
        try:
            reply = self.client.read(block)
            observed = self.now()
            raw_words = tuple(reply.words)
            if reply.offset != block.offset:
                raise ProtocolError("response register block mismatch")
            decoded = decode_register_block(reply.offset, raw_words)
            decoded = tuple(item for item in decoded if item.signal_id not in self.blocked_signals)
            counter = next(
                (item for item in decoded if item.signal_id == "boiler.operating_minutes" and item.quality == "ok"),
                None,
            )
            if counter is not None and self._last_counter is not None:
                previous_value, previous_time = self._last_counter
                try:
                    validate_operating_counter_progression(
                        previous_value, counter.value, observed - previous_time
                    )
                except DecodeError as exc:
                    decoded = tuple(
                        replace(item, quality="invalid", error_code=exc.code, error_message=str(exc))
                        if item.signal_id == counter.signal_id else item
                        for item in decoded
                    )
                    counter = None
            has_error = any(item.quality != "ok" for item in decoded)
            request.update(
                completed_at=observed.isoformat(), outcome="error" if has_error else "ok",
                error_class="SignalValueError" if has_error else None,
            )
            self._record_observations(request, decoded, observed)
            if counter is not None:
                self._last_counter = (counter.value, observed)
            self._advance_block(block)
            self._reconnect_attempts = 0
            self.error = None
            self._retry_at = None
            self.state = "running"
            self._last_action = f"Next register block at offset {self._next_offset}"
        except ModbusExceptionError as exc:
            completed = self.now()
            code = f"modbus_exception_{exc.exception_code}"
            explanation = {
                1: "Lesefunktion nicht unterstützt",
                2: "Registeradresse nicht verfügbar",
                3: "Registerabfrage vom Gerät abgelehnt",
                4: "Gerätefehler bei der Registerabfrage",
                5: "Gerät hat die Abfrage noch nicht abgeschlossen",
                6: "Gerät ist beschäftigt",
                8: "Gerät meldet einen Speicherprüffehler",
                10: "Modbus-Gateway-Pfad nicht verfügbar",
                11: "Modbus-Gateway erhält keine Geräteantwort",
            }.get(exc.exception_code, "Gerät hat den Registerblock abgelehnt")
            register_error = exc.exception_code in (2, 3)
            message = (
                f"{explanation} (Modbus-Ausnahme {exc.exception_code}). "
                + ("Auslesung ausgesetzt; Ursache vor erneuter Freigabe prüfen."
                   if register_error else "Erfassung angehalten; Geräteursache prüfen.")
            )
            request.update(completed_at=completed.isoformat(), error_class=type(exc).__name__)
            self._record_observations(
                request, self._block_errors(block, (), code, message, "invalid"), completed,
                quarantine=register_error,
            )
            self._reconnect_attempts = 0
            self.error = None
            if register_error:
                self._advance_block(block)
            else:
                self.error = message
                self._stop.set()
            self._retry_at = None
            self.state = "running" if register_error else "stopped_protocol"
            self._last_action = (
                "Registerblock ausgesetzt; übrige Signale werden weiter erfasst"
                if register_error else "Gerätefehler prüfen; keine automatischen Folgeabfragen"
            )
        except (ModbusError, DecodeError) as exc:
            completed = self.now()
            request.update(completed_at=completed.isoformat(), error_class=type(exc).__name__)
            if isinstance(exc, ModbusConnectionError):
                code, quality = "transport_error", "unavailable"
                message = "Keine vollständige Verbindung zum Gerät; Registerabfrage fehlgeschlagen."
            elif isinstance(exc, DecodeError):
                code, quality = exc.code, "invalid"
                message = "Ungültige Registerblockdaten; Erfassung zur Ursachenprüfung angehalten."
            else:
                code, quality = "protocol_error", "invalid"
                message = "Unvollständige oder fehlerhafte Modbus-Antwort; Erfassung zur Ursachenprüfung angehalten."
            self._record_observations(
                request, self._block_errors(block, raw_words, code, message, quality),
                completed, quarantine=False,
            )
            self.error = message
            if self._read_to_clear(block) and isinstance(exc, ModbusConnectionError):
                self.state = "stopped_transport"
                self._retry_at = None
                self._last_action = "Read-to-clear-Auslesung fehlgeschlagen; keine automatische Wiederholung"
            elif isinstance(exc, (ProtocolError, IncompleteResponseError)):
                self.state = "stopped_protocol"
                self._last_action = "Acknowledge after protocol cause is resolved"
            elif isinstance(exc, ModbusConnectionError):
                if not self.retry_on_transport_error:
                    self.state = "stopped_transport"
                    self._retry_at = None
                    self._last_action = "Finite collection stopped after transport error"
                else:
                    self.state = "reconnect_wait"
                    self._retry_at = completed + timedelta(seconds=self._block_interval(block))
                    self._last_action = "Nächste Abfrage im regulären Intervall; kein Versuchslimit"
                    self._advance_block(block)
            else:
                self.state = "stopped_data"
                self._last_action = "Acknowledge after data cause is resolved"
            if self.state != "reconnect_wait":
                self._stop.set()
            self.store.record_event(
                str(uuid4()), completed.isoformat(), "collector_state_changed", "error",
                message,
                {"state": self.state, "error_code": code, "block_offset": block.offset,
                 "signal_ids": list(block.signal_ids)},
            )
        finally:
            # Reserve the next interval only after variable disk/network latency has elapsed.
            self._last_completed[block.offset] = self.monotonic()
            self._last_completed_at[block.offset] = self.now()
            self._request_in_flight = False
            if self._paused.is_set() and self.state in {"running", "reconnect_wait"}:
                self.state = "paused"
                self._last_action = "Collection paused"
            self._persist_state()

    @staticmethod
    def _block_errors(block, raw_words, code, message, quality):
        return tuple(
            DecodedSignal(
                signal_id, None, SIGNAL_DEFINITIONS[signal_id]["unit"], block.offset, raw_words,
                profile_id=PROFILE_ID if block in CORE_PROFILE else "extended",
                quality=quality, error_code=code, error_message=message,
            )
            for signal_id in block.signal_ids
        )

    def _record_observations(self, request, decoded, observed, *, quarantine=False) -> None:
        selected = self._selected_signals()
        active = tuple(item for item in decoded if item.signal_id not in self.blocked_signals)
        observations = [
            {
                "observation_id": str(uuid4()), "signal_id": item.signal_id,
                "observed_at": observed.isoformat(), "value": item.value,
                "unit": item.unit, "quality": item.quality, "raw_words": item.raw_words,
                "source": item.source, "profile_id": item.profile_id,
                "profile_version": item.profile_version, "decoder_version": item.decoder_version,
                "error_code": item.error_code, "error_message": item.error_message,
            }
            for item in active if item.signal_id in selected
        ]
        self.store.record_cycle(request, observations)
        for item in active:
            if item.signal_id not in selected:
                continue
            if quarantine and item.quality == "invalid":
                self.blocked_signals.add(item.signal_id)
            if item.error_code is not None:
                if self._signal_errors.get(item.signal_id) != item.error_code:
                    self.store.record_event(
                        str(uuid4()), observed.isoformat(), "signal_quality_changed", "error",
                        item.error_message,
                        {"signal_id": item.signal_id, "error_code": item.error_code,
                         "block_offset": item.offset},
                    )
                self._signal_errors[item.signal_id] = item.error_code
            else:
                self._signal_errors.pop(item.signal_id, None)

    def _persist_state(self) -> None:
        self.store.save_collector_state(
            {
                "state": self.state,
                "request_count": self._request_count,
                "max_requests": self.max_requests,
                "max_duration_seconds": self.max_duration_seconds,
                "error": self.error,
                "profile_id": PROFILE_ID,
                "configuration_id": self._endpoint_id,
                "reconnect_attempts": self._reconnect_attempts,
                "retry_at": self.status()["next_action_at"],
                "retry_block_offset": self._retry_block_offset,
                "next_offset": self._next_offset,
                "next_action": self._last_action,
                "request_in_flight": self._request_in_flight,
                "blocked_signals": sorted(self.blocked_signals),
                "last_completed_at": {
                    str(offset): completed.isoformat()
                    for offset, completed in self._last_completed_at.items()
                },
                "logging_revision": self._logging_config["revision"],
            },
            self.now().isoformat(),
        )

    def _persist_state_best_effort(self) -> None:
        try:
            self._persist_state()
        except StorageError:
            pass
