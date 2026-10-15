"""Endliche manuelle Diagnose; keine Geräteaktion ohne persistente Reservierung."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from typing import Callable, Literal

from backend.catalog import CatalogSelectionError, CatalogUnavailable, build_read_blocks, load_catalog
from backend.collector import Collector
from backend.config import Settings
from backend.device_lock import DeviceLock, DeviceOwnershipError
from backend.modbus import (
    ConnectionError as TransportError, IncompleteResponseError, ModbusTcpClient, ProtocolError,
)
from backend.registers import (
    CORE_PROFILE, DecodeError, decode_register_block, validate_operating_counter_progression,
)
from backend.storage import SQLiteStore, StorageError, utc_now


class ReadCheckError(RuntimeError):
    """Öffentlicher Fehlercode ohne private Ziel-/Speicherdetails."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def target_fingerprint(settings: Settings, catalog_sha256: str) -> str:
    """Private Planbindung; niemals als öffentliche Identität verwenden."""
    return hashlib.sha256(json.dumps({
        "host": (settings.modbus_host or "").casefold(), "port": settings.modbus_port,
        "unit_id": settings.modbus_unit_id, "source": settings.diagnostics_source,
        "catalog_sha256": catalog_sha256,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ReadCheckRunner:
    def __init__(self, *, settings: Settings, store: SQLiteStore,
                 collector: Collector | None, client: ModbusTcpClient | None = None,
                 monotonic: Callable[[], float] = time.perf_counter,
                 now: Callable[[], datetime] | None = None):
        self.settings, self.store, self.collector = settings, store, collector
        self.client = client
        self.monotonic, self.now = monotonic, now
        self.mode_lock = threading.RLock()
        self.stop_event = threading.Event()
        if collector is not None:
            collector.mode_lock = self.mode_lock
        self._device_lock = DeviceLock(settings.data_dir / "collector.lock")
        self._run_id: str | None = None
        self._deadline = 0.0
        self._due = 0.0
        self._watchdog: threading.Thread | None = None
        self._workers: list[threading.Thread] = []
        self._closed = False
        self._storage_failed = False
        self._recovery_conflict = False

    def _timestamp(self) -> str:
        if self.now is None:
            return utc_now()
        value = self.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTC clock must be timezone aware")
        return value.astimezone(timezone.utc).isoformat()

    @contextmanager
    def _action(self):
        with self.mode_lock:
            if self._storage_failed:
                raise ReadCheckError("stopped_storage")
            try:
                yield
            except StorageError:
                self._storage_failed = True
                self.stop_event.set()
                if self._run_id is not None:
                    try:
                        self.store.set_diagnostic_run_state(
                            self._run_id, "stopped_storage", "storage_error",
                        )
                    except StorageError:
                        pass
                    self._release()
                raise ReadCheckError("stopped_storage") from None

    def _get(self, run_id: str) -> dict:
        run = self.store.get_diagnostic_run(run_id)
        if run is None:
            raise ReadCheckError("run_conflict")
        return run

    def _binding(self, run: dict):
        settings = self.settings
        if not settings.modbus_host:
            raise ReadCheckError("unconfigured")
        if settings.modbus_unit_id != 255:
            raise ReadCheckError("invalid_unit")
        if settings.diagnostics_source == "simulator" and settings.modbus_host != "127.0.0.1":
            raise ReadCheckError("plan_changed")
        try:
            catalog = load_catalog()
            blocks = build_read_blocks(run["plan"]["register_ids"])
        except (CatalogUnavailable, CatalogSelectionError):
            raise ReadCheckError("catalog_unavailable") from None
        plan = run["plan"]
        fingerprint = target_fingerprint(settings, catalog.sha256)
        if (plan["target_fingerprint"] != fingerprint
                or plan["catalog_sha256"] != catalog.sha256
                or plan["source"] != settings.diagnostics_source
                or plan["target"]["host"].casefold() != settings.modbus_host.casefold()
                or plan["target"]["port"] != settings.modbus_port
                or plan["blocks"] != [{"offset": b.offset, "count": b.count} for b in blocks]):
            raise ReadCheckError("plan_changed")
        return blocks

    def _core_clean(self, *, joined: bool = False):
        if self.collector is not None:
            c = self.collector
            if (c.state not in ({"paused", "completed"} if joined else {"running", "paused", "completed"})
                    or c.error or c.status()["reconnect_attempts"]):
                raise ReadCheckError("core_blocked")
        saved = self.store.get_collector_state()
        if saved is not None and (
            saved.get("error") or saved.get("reconnect_attempts", 0)
            or saved.get("retry_at") or saved.get("retry_delay_seconds") is not None
            or (joined and saved.get("request_in_flight"))
            or saved.get("state") not in (
                {"paused", "completed"} if joined or self.collector is None
                else {"running", "paused", "completed"}
            )
        ):
            raise ReadCheckError("core_blocked")

    def start(self, run_id: str) -> dict:
        with self._action():
            if self._closed or self._run_id is not None or self._recovery_conflict:
                raise ReadCheckError("run_conflict")
            run = self._get(run_id)
            if run["state"] != "planned" or self.store.diagnostic_access_blocker():
                raise ReadCheckError("run_conflict")
            self._binding(run)
            self._core_clean()
            if self.collector is not None:
                try:
                    self.collector.stop()
                except TimeoutError:
                    raise ReadCheckError("run_conflict") from None
            self._core_clean(joined=True)
            self._device_lock.acquire()
            try:
                run = self._get(run_id)
                if run["state"] != "planned" or self.store.diagnostic_access_blocker():
                    raise ReadCheckError("run_conflict")
                self._binding(run)
                self._core_clean(joined=True)
                self.store.set_diagnostic_run_state(run_id, "running", None)
                self._run_id = run_id
                self.stop_event = threading.Event()
                started = self.monotonic()
                self._deadline, self._due = started + 600, started + 60
                self._watchdog = threading.Thread(
                    target=self._watch, args=(run_id, self.stop_event, self._deadline),
                    name="sommerauer-read-check-watchdog", daemon=True,
                )
                self._workers.append(self._watchdog)
                self._watchdog.start()
                return self._public(self._get(run_id))
            except BaseException:
                self._device_lock.release()
                raise

    def _watch(self, run_id: str, stop_event: threading.Event, deadline: float):
        # Kurzes Warten prüft nur die Frist; auch injizierte monotone Uhren bleiben wirksam.
        while not stop_event.wait(min(1.0, max(0.0, deadline - self.monotonic()))):
            if self.monotonic() >= deadline:
                stop_event.set()
                break
        with self.mode_lock:
            if self._run_id == run_id:
                try:
                    self._end("expired" if self.monotonic() >= self._deadline else "cancelled")
                except StorageError:
                    self._storage_failed = True
                    self._release()

    def _release(self):
        self.stop_event.set()
        self._device_lock.release()
        self._run_id = None

    def _end(self, state: str, reason: str | None = None):
        if self._run_id is not None:
            try:
                self.store.set_diagnostic_run_state(self._run_id, state, reason or state)
            finally:
                self._release()

    def _active(self, run_id: str) -> dict:
        if self._closed or self._run_id != run_id:
            raise ReadCheckError("run_conflict")
        run = self._get(run_id)
        if self.stop_event.is_set() or self.monotonic() >= self._deadline:
            self._end("expired" if self.monotonic() >= self._deadline else "cancelled")
            raise ReadCheckError("run_conflict")
        return run

    def _counter_check(self, run: dict, value: int, completed_at: str):
        previous = self.store.last_diagnostic_counter(run["plan"]["target_fingerprint"])
        if previous is not None:
            validate_operating_counter_progression(
                previous["value"], value,
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(previous["completed_at"]),
            )

    def _active_binding(self, run: dict):
        try:
            return self._binding(run)
        except ReadCheckError as exc:
            # Ein festgestellter Bindungs-/Katalogfehler beendet auch ohne Socket den Lauf.
            self._end("stopped_data", exc.code)
            raise

    def read_next(self, run_id: str, step_index: int) -> dict:
        with self._action():
            run = self._active(run_id)
            if (type(step_index) is not int or run["state"] != "running"
                    or step_index != run["requests_reserved"]
                    or not 0 <= step_index < run["plan"]["request_budget"]):
                raise ReadCheckError("run_conflict")
            blocks = self._active_binding(run)
            if self.monotonic() < self._due:
                raise ReadCheckError("read_not_due")
            # Nochmals unmittelbar vor der unumkehrbaren Reservierung prüfen.
            self._active(run_id)
            self._active_binding(run)
            self.store.reserve_diagnostic_request(run_id, step_index, self._timestamp())
            raw = None
            decoded = None
            received = 0
            error = None
            state = "awaiting_review"
            outcome = "ok"
            try:
                if self.stop_event.is_set() or self.monotonic() >= self._deadline:
                    state = "expired" if self.monotonic() >= self._deadline else "cancelled"
                    outcome = "aborted"
                else:
                    self._binding(run)
                    block = blocks[step_index]
                    if self.client is None:
                        self.client = ModbusTcpClient(self.settings.modbus_host, self.settings.modbus_port)
                    answer = self.client.read_catalog(block)
                    raw = list(answer.words)
                    received = 9 + 2 * len(raw)
                    if (answer.offset != block.offset or answer.unit_id != 255
                            or answer.function_code != 3 or len(raw) != block.count
                            or any(type(w) is not int or not 0 <= w <= 65535 for w in raw)):
                        raise ProtocolError("invalid_response", received_bytes=received)
                    core = next((c for c in CORE_PROFILE
                                 if (c.offset, c.count) == (block.offset, block.count)), None)
                    if core is not None:
                        signals = decode_register_block(block.offset, raw)
                        if block.offset == 28688:
                            self._counter_check(run, signals[0].value, self._timestamp())
                        decoded = [asdict(signal) for signal in signals]
            except TransportError as exc:
                state, error, received = "stopped_transport", "transport_error", exc.received_bytes
            except (ProtocolError, IncompleteResponseError) as exc:
                state, error, received = "stopped_protocol", "protocol_error", exc.received_bytes
            except DecodeError as exc:
                state, error = "stopped_data", exc.code
            except ReadCheckError as exc:
                state, error = "stopped_data", exc.code
            except StorageError:
                raise
            except Exception:
                state, error = "stopped_data", "unexpected_error"
            if error is not None:
                outcome, decoded = "error", None
            elif self.stop_event.is_set() or self.monotonic() >= self._deadline:
                state = "expired" if self.monotonic() >= self._deadline else "cancelled"
            self.store.finish_diagnostic_request(run_id, step_index, {
                "outcome": outcome, "raw_words": raw, "decoded": decoded,
                "error_class": error, "received_bytes": received,
                "completed_at": self._timestamp(),
            }, state)
            self._due = self.monotonic() + 60
            # Ein Stopp während der Speichertransaktion darf keinen weiteren Read erlauben.
            if state == "awaiting_review" and (
                self.stop_event.is_set() or self.monotonic() >= self._deadline
            ):
                self._end("expired" if self.monotonic() >= self._deadline else "cancelled")
            elif state != "awaiting_review":
                self._release()
            return self._public(self._get(run_id))

    def review(self, run_id: str, step_index: int,
               verdict: Literal["continue", "finish", "anomaly"], observation: str | None) -> dict:
        with self._action():
            run = self._active(run_id)
            if (run["state"] != "awaiting_review" or type(step_index) is not int
                    or step_index != run["requests_reserved"] - 1
                    or verdict not in {"continue", "finish", "anomaly"}
                    or (observation is not None and not isinstance(observation, str))):
                raise ReadCheckError("run_conflict")
            state = {"continue": "completed" if run["requests_reserved"] == run["plan"]["request_budget"]
                     else "running", "finish": "cancelled", "anomaly": "stopped_data"}[verdict]
            self.store.review_diagnostic_request(
                run_id, step_index, {"verdict": verdict, "observation": observation}, state,
            )
            if state != "running":
                self._release()
            return self._public(self._get(run_id))

    def stop(self, run_id: str) -> dict:
        if self._run_id == run_id:
            self.stop_event.set()
        with self._action():
            run = self._get(run_id)
            if self._run_id == run_id:
                self._end("expired" if self.monotonic() >= self._deadline else "cancelled")
            elif run["state"] in {"planned", "running", "awaiting_review"}:
                raise ReadCheckError("run_conflict")
            return self._public(self._get(run_id))

    def recover_interrupted(self) -> None:
        with self.mode_lock:
            if self._run_id is not None or self._closed:
                raise ReadCheckError("run_conflict")
            try:
                self._device_lock.acquire()
            except DeviceOwnershipError:
                self._recovery_conflict = True
                raise
            try:
                self.store.interrupt_active_diagnostic_runs()
                self._storage_failed = False
                self._recovery_conflict = False
            except StorageError:
                self._storage_failed = True
                raise ReadCheckError("stopped_storage") from None
            finally:
                self._device_lock.release()

    def close(self) -> None:
        self.stop_event.set()
        with self.mode_lock:
            self._closed = True
            try:
                self._end("cancelled")
            except StorageError:
                self._storage_failed = True
        for worker in self._workers:
            if worker is not threading.current_thread():
                worker.join()

    def access_blocker(self) -> str | None:
        """Lesender gemeinsamer Zugriffsschutz, auch nach fehlgeschlagener Recovery."""
        with self.mode_lock:
            if self._storage_failed:
                return "storage_unavailable"
            if self._closed or self._recovery_conflict:
                return "run_conflict"
            blocking_id = self.store.diagnostic_access_blocker()
            if blocking_id is None:
                return None
            run = self.store.get_diagnostic_run(blocking_id)
            if run is not None and run["state"] in {"running", "awaiting_review"}:
                return "run_conflict"
            return "diagnostic_stop_unacknowledged"

    def status(self, run_id: str) -> dict:
        """Reine Statusprojektion; keine Recovery, Bindungsprüfung oder Geräteaktion."""
        with self.mode_lock:
            run = self._get(run_id)
            active = self._run_id == run_id
            remaining = max(0.0, self._deadline - self.monotonic()) if active else 0.0
            next_step = (
                run["requests_reserved"] if run["state"] in {"planned", "running"}
                and run["requests_reserved"] < run["plan"]["request_budget"] else None
            )
            return {
                **self._public(run),
                "next_step_index": next_step,
                "wait_remaining_seconds": max(0.0, self._due - self.monotonic()) if active else 0.0,
                "duration_remaining_seconds": remaining,
            }

    @staticmethod
    def request_evidence(request: dict) -> dict:
        """Öffentlicher Antwortbeleg; Betreiberbewertung bleibt separat."""
        item = {key: request[key] for key in (
            "step_index", "outcome", "started_at", "completed_at", "raw_words",
            "error_class", "received_bytes", "review",
        )}
        item["decoded_signals"] = request["decoded"] or []
        item["interpretation_status"] = "confirmed_core" if request["decoded"] is not None else "raw_only"
        return item

    @staticmethod
    def _public(run: dict) -> dict:
        return {"run_id": run["run_id"], "state": run["state"],
                "requests_reserved": run["requests_reserved"],
                "requests": [ReadCheckRunner.request_evidence(item) for item in run["requests"]],
                "source": run["plan"]["source"]}
