"""Single-owner, bounded collector for the confirmed core register profile."""

from __future__ import annotations

from datetime import datetime, timezone
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
    ModbusTcpClient,
    ProtocolError,
)
from backend.registers import (
    CORE_PROFILE,
    PROFILE_ID,
    DecodeError,
    decode_register_block,
    validate_operating_counter_progression,
)
from backend.storage import SQLiteStore, StorageError

MIN_REQUEST_GAP_SECONDS = 10.0
MIN_BLOCK_INTERVAL_SECONDS = 60.0


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
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[threading.Event, float], bool] | None = None,
        now: Callable[[], datetime] | None = None,
        max_duration_seconds: float | None = None,
        max_requests: int | None = None,
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
        self._lock = _ProcessLock(data_dir / "collector.lock")
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._request_count = 0
        self._last_request_end: float | None = None
        self._last_started: dict[int, float] = {}
        self._last_counter: tuple[int, datetime] | None = None
        self.state = "paused"
        self.error: str | None = None

    def start(self) -> None:
        """Acquire ownership before creating the background worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._lock.acquire()
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self.run, name="sommerauer-collector", daemon=True)
        self._thread.start()

    def run(self) -> None:
        """Run until stopped, paused, failed, or a configured finite limit is reached."""
        try:
            if self._thread is None:
                self._lock.acquire()
            self.state = "running"
            self._started_at = self.monotonic()
            self._persist_state()
            while not self._stop.is_set():
                if self._paused.is_set():
                    self.state = "paused"
                    self._persist_state()
                    if self.wait(self._stop, 0.1):
                        break
                    continue
                if self._limit_reached():
                    self.state = "completed"
                    self._persist_state()
                    break
                block = self._next_block()
                due = self._due_at(block)
                if self.max_duration_seconds is not None and self._started_at is not None:
                    due = min(due, self._started_at + self.max_duration_seconds)
                if not self._wait_until(due):
                    break
                if self._stop.is_set() or self._paused.is_set():
                    continue
                if self._limit_reached():
                    self.state = "completed"
                    self._persist_state()
                    break
                self._read_one(block)
            if self.state == "running":
                self.state = "stopped"
                self._persist_state()
        except CollectorOwnershipError:
            self.state = "ownership_error"
            self.error = "collector lock is held by another process"
            raise
        except StorageError as exc:
            self.state = "stopped_storage"
            self.error = str(exc)
            self._persist_state_best_effort()
        finally:
            self._lock.release()

    def pause(self) -> None:
        """Pause future reads; an in-flight read may finish by its transport deadline."""
        self._paused.set()

    def resume(self) -> None:
        if self.state in {"stopped_storage", "protocol_error", "data_error", "ownership_error"}:
            raise CollectorStopped(f"cannot resume collector in state {self.state}")
        self._paused.clear()

    def stop(self, timeout: float | None = 4.0) -> None:
        """Prevent new reads, allow an in-flight request to finish, then join the worker."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise TimeoutError("collector did not stop before the join timeout")
            self._thread = None
        if self.state not in {"stopped_storage", "protocol_error", "data_error", "ownership_error", "completed"}:
            self.state = "paused"
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

    def _next_block(self):
        return CORE_PROFILE[self._request_count % len(CORE_PROFILE)]

    def _due_at(self, block) -> float:
        due = self._started_at if self._started_at is not None else self.monotonic()
        previous = self._last_started.get(block.offset)
        if previous is not None:
            due = max(due, previous + MIN_BLOCK_INTERVAL_SECONDS)
        if self._last_request_end is not None:
            due = max(due, self._last_request_end + MIN_REQUEST_GAP_SECONDS)
        return due

    def _wait_until(self, due: float) -> bool:
        while not self._stop.is_set() and self.monotonic() < due:
            if self.wait(self._stop, due - self.monotonic()):
                return False
        return not self._stop.is_set()

    def _read_one(self, block) -> None:
        started = self.now()
        started_mono = self.monotonic()
        self._last_started[block.offset] = started_mono
        self._request_count += 1
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
        try:
            reply = self.client.read(block)
            observed = self.now()
            decoded = decode_register_block(reply.offset, reply.words)
            counter = next((item for item in decoded if item.signal_id == "boiler.operating_minutes"), None)
            if counter is not None and self._last_counter is not None:
                previous_value, previous_time = self._last_counter
                validate_operating_counter_progression(
                    previous_value, counter.value, observed - previous_time
                )
            observations = [
                {
                    "observation_id": str(uuid4()),
                    "signal_id": item.signal_id,
                    "observed_at": observed.isoformat(),
                    "value": item.value,
                    "unit": item.unit,
                    "quality": "ok",
                    "raw_words": item.raw_words,
                    "source": item.source,
                    "profile_id": item.profile_id,
                    "profile_version": item.profile_version,
                    "decoder_version": item.decoder_version,
                }
                for item in decoded
            ]
            request.update(completed_at=observed.isoformat(), outcome="ok")
            self.store.record_cycle(request, observations)
            if counter is not None:
                self._last_counter = (counter.value, observed)
        except (ModbusError, DecodeError) as exc:
            completed = self.now()
            request.update(completed_at=completed.isoformat(), error_class=type(exc).__name__)
            self.store.record_cycle(request, [])
            self.error = str(exc)
            if isinstance(exc, (ProtocolError, IncompleteResponseError)):
                self.state = "protocol_error"
            elif isinstance(exc, ModbusConnectionError):
                self.state = "transport_error"
            else:
                self.state = "data_error"
            self.store.record_event(
                str(uuid4()), completed.isoformat(), "collector_stopped", "error",
                "Collector stopped after a read or data error", {"error_class": type(exc).__name__},
            )
            self._stop.set()
        finally:
            self._last_request_end = self.monotonic()
            self._persist_state()

    def _persist_state(self) -> None:
        self.store.save_collector_state(
            {
                "state": self.state,
                "request_count": self._request_count,
                "max_requests": self.max_requests,
                "max_duration_seconds": self.max_duration_seconds,
                "error": self.error,
                "profile_id": PROFILE_ID,
            },
            self.now().isoformat(),
        )

    def _persist_state_best_effort(self) -> None:
        try:
            self._persist_state()
        except StorageError:
            pass
