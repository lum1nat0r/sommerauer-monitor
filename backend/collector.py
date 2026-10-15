"""Single-owner, bounded collector for the confirmed core register profile."""

from __future__ import annotations

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

MIN_BLOCK_INTERVAL_SECONDS = 60.0
RECONNECT_DELAYS_SECONDS = (60.0, 120.0, 300.0, 600.0, 900.0)
MAX_RECONNECT_ATTEMPTS = len(RECONNECT_DELAYS_SECONDS)



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
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._request_count = 0
        self._last_started: dict[int, float] = {}
        self._last_counter: tuple[int, datetime] | None = None
        self._endpoint_id = self._configuration_id(host, port)
        self._next_offset = CORE_PROFILE[0].offset
        self._retry_block_offset = CORE_PROFILE[0].offset
        self._reconnect_attempts = 0
        self._successful_core_cycles = 0
        self._successful_blocks_in_cycle = 0
        self._retry_at: datetime | None = None
        self._retry_delay_seconds: float | None = None
        self._last_action: str | None = None
        self._retry_monotonic_deadline: float | None = None
        self._request_in_flight = False
        self.state = "paused"
        self.error: str | None = None
        self._has_saved_state = False
        self._restore_state()
        if self.state == "paused":
            self._paused.set()

    @staticmethod
    def _configuration_id(host: str, port: int) -> str:
        import hashlib

        return hashlib.sha256(f"{host.casefold()}:{port}:255:{PROFILE_ID}".encode()).hexdigest()

    def status(self) -> dict[str, Any]:
        reasons = {
            "running": "Wiederaufnahme erfolgreich; Budget-Reset nach drei Kernzyklen",
            "reconnect_wait": "Verbindungsfehler; begrenzte Wiederaufnahme geplant",
            "stopped_transport": "Wiederaufnahmebudget ausgeschöpft",
            "stopped_protocol": "Protokollfehler; Erfassung angehalten",
            "stopped_data": "Datenfehler; Erfassung angehalten",
            "stopped_storage": "Speicher- oder Zustandsfehler; Erfassung angehalten",
            "paused": "Erfassung pausiert",
        }
        next_action_at = self._retry_at
        if self.state == "reconnect_wait" and self._retry_monotonic_deadline is not None:
            remaining = max(0.0, self._retry_monotonic_deadline - self.monotonic())
            next_action_at = self.now() + timedelta(seconds=remaining)
        return {
            "state": self.state,
            "reason": reasons.get(self.state) if self.error else None,
            "reconnect_attempts": self._reconnect_attempts,
            "reconnect_attempt_limit": MAX_RECONNECT_ATTEMPTS,
            "next_action_at": next_action_at.isoformat() if next_action_at else None,
            "next_action": self._last_action,
            "profile_id": PROFILE_ID,
        }

    def _restore_state(self) -> None:

        try:
            saved = self.store.get_collector_state()
        except StorageError as exc:
            self.state = "stopped_storage"
            self.error = f"Could not restore collector state: {exc}"
            self._last_action = "Inspect storage; no automatic reads"
            return
        self._has_saved_state = saved is not None
        if saved is None:
            self._last_action = "Start collection"
            return
        try:
            if saved["configuration_id"] != self._endpoint_id or saved["profile_id"] != PROFILE_ID:
                self.error = "Saved state belongs to a different target or profile"
                self._last_action = "Review configuration and acknowledge"
                return
            self.state = saved["state"]
            self.error = saved.get("error")
            self._request_count = int(saved.get("request_count", 0))
            self._reconnect_attempts = int(saved.get("reconnect_attempts", 0))
            self._successful_core_cycles = int(saved.get("successful_core_cycles", 0))
            self._successful_blocks_in_cycle = int(saved.get("successful_blocks_in_cycle", 0))
            self._next_offset = int(saved.get("next_offset", CORE_PROFILE[0].offset))
            self._retry_block_offset = int(saved.get("retry_block_offset", CORE_PROFILE[0].offset))
            valid_offsets = {block.offset for block in CORE_PROFILE}
            if (
                not 0 <= self._reconnect_attempts <= MAX_RECONNECT_ATTEMPTS
                or not 0 <= self._successful_core_cycles < 3
                or not 0 <= self._successful_blocks_in_cycle < len(CORE_PROFILE)
                or self._next_offset not in valid_offsets
                or self._retry_block_offset not in valid_offsets
            ):
                raise ValueError("persisted recovery counters or block offsets are invalid")
            self._last_action = saved.get("next_action")
            self._retry_delay_seconds = (
                float(saved["retry_delay_seconds"])
                if saved.get("retry_delay_seconds") is not None else None
            )
            if self.state == "paused" and self._retry_delay_seconds is not None:
                self._retry_at = self.now() + timedelta(seconds=self._retry_delay_seconds)
                self._retry_monotonic_deadline = self.monotonic() + self._retry_delay_seconds
            if self.state in {"reconnect_wait", "running"}:
                in_flight = self.state == "running" and saved.get("request_in_flight", False)
                if self.state == "running" and not in_flight:
                    self._retry_block_offset = self._next_offset
                if in_flight:
                    self._successful_core_cycles = 0
                    self._successful_blocks_in_cycle = 0
                    self.error = "Request outcome was uncertain at process restart"
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                        self.state = "stopped_transport"
                        self.error = "Interrupted request exhausted the recovery budget"
                        self._last_action = "Acknowledge after resolving interrupted requests"
                        self._retry_at = None
                        self._retry_delay_seconds = None
                        self._successful_blocks_in_cycle = 0
                        self._paused.set()
                        return
                    delay = RECONNECT_DELAYS_SECONDS[self._reconnect_attempts - 1]
                elif self.state == "running":
                    delay = RECONNECT_DELAYS_SECONDS[
                        min(self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS - 1)
                    ]
                else:
                    delay = self._retry_delay_seconds or RECONNECT_DELAYS_SECONDS[0]
                self._retry_delay_seconds = delay
                self._retry_at = self.now() + timedelta(seconds=delay)
                self._retry_monotonic_deadline = self.monotonic() + delay
                self.state = "reconnect_wait"
                self._last_action = "Retry same core block after a conservative restart delay"
            elif self.state not in {
                "paused", "stopped_transport", "stopped_protocol", "stopped_data",
                "stopped_storage", "completed",
            }:
                raise ValueError("unknown persisted collector state")
        except (KeyError, TypeError, ValueError, OverflowError):
            self.state = "stopped_storage"
            self.error = "Persisted collector state is invalid"
            self._retry_at = None
            self._last_action = "Inspect persisted state; no automatic reads"
        if self.state != "reconnect_wait":
            self._paused.set()

    def acknowledge_and_start(self) -> None:
        if self.state not in {
            "paused", "stopped_transport", "stopped_protocol", "stopped_data",
            "stopped_storage", "completed",
        }:
            raise CollectorStopped(f"cannot acknowledge collector in state {self.state}")
        self.error = None
        self._reconnect_attempts = 0
        self._successful_core_cycles = 0
        self._successful_blocks_in_cycle = 0
        self._retry_at = None
        self._retry_delay_seconds = None
        self._retry_monotonic_deadline = None
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
                recovering = self.state == "reconnect_wait"
                if recovering:
                    if self._retry_at is None or self._retry_monotonic_deadline is None:
                        raise StorageError("Reconnect state has no retry deadline")
                    remaining = self._retry_monotonic_deadline - self.monotonic()
                    if remaining > 0 and not self._wait_until(self.monotonic() + remaining):
                        break
                    if self._stop.is_set() or self._paused.is_set():
                        continue
                    block = self._block_by_offset(self._retry_block_offset)
                    self._reconnect_attempts += 1
                    self.state = "running"
                    self._last_action = "Attempting bounded recovery read"
                    self._retry_at = None
                    self._retry_monotonic_deadline = None
                    self._persist_state()
                else:
                    block = self._block_by_offset(self._next_offset)
                    if not self._wait_until(self._due_at(block)):
                        break
                    if self._stop.is_set() or self._paused.is_set():
                        continue
                    if self._limit_reached():
                        self.state = "completed"
                        self._last_action = "Finite collection limit reached"
                        self._persist_state()
                        break
                self._read_one(block, recovery=recovering)
            if self.state == "running":
                self.state = "paused"
                self._last_action = "Collection paused"
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
            "Resume after saved retry delay"
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
        for block in CORE_PROFILE:
            if block.offset == offset:
                return block
        raise StorageError("Persisted collector block is outside the core profile")

    def _due_at(self, block) -> float:
        due = self._started_at if self._started_at is not None else self.monotonic()
        previous = self._last_started.get(block.offset)
        if previous is not None:
            due = max(due, previous + MIN_BLOCK_INTERVAL_SECONDS)
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

    def _read_one(self, block, *, recovery: bool = False) -> None:
        started = self.now()
        started_mono = self.monotonic()
        self._last_started[block.offset] = started_mono
        self._request_count += 1
        self._retry_block_offset = block.offset
        self.state = "running"
        self._request_in_flight = True
        self._last_action = f"Read core block at offset {block.offset}"
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
            self._next_offset = CORE_PROFILE[
                (next(i for i, candidate in enumerate(CORE_PROFILE) if candidate.offset == block.offset) + 1)
                % len(CORE_PROFILE)
            ].offset
            expected = CORE_PROFILE[self._successful_blocks_in_cycle].offset
            if block.offset == expected:
                self._successful_blocks_in_cycle += 1
            elif block.offset == CORE_PROFILE[0].offset:
                self._successful_blocks_in_cycle = 1
            else:
                self._successful_blocks_in_cycle = 0
            if self._successful_blocks_in_cycle == len(CORE_PROFILE):
                self._successful_core_cycles += 1
                self._successful_blocks_in_cycle = 0
                if self._successful_core_cycles >= 3:
                    self._reconnect_attempts = 0
                    self._successful_core_cycles = 0
                    self.error = None
            if recovery:
                self._retry_at = None
                self._retry_delay_seconds = None
                self._retry_monotonic_deadline = None
            self.state = "running"
            self._last_action = f"Next core block at offset {self._next_offset}"
        except (ModbusError, DecodeError) as exc:
            completed = self.now()
            request.update(completed_at=completed.isoformat(), error_class=type(exc).__name__)
            self.store.record_cycle(request, [])
            self.error = str(exc)
            self._successful_core_cycles = 0
            self._successful_blocks_in_cycle = 0
            if isinstance(exc, (ProtocolError, IncompleteResponseError)):
                self.state = "stopped_protocol"
                self._last_action = "Acknowledge after protocol cause is resolved"
            elif isinstance(exc, ModbusConnectionError):
                self._retry_block_offset = block.offset
                if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                    self.state = "stopped_transport"
                    self._retry_at = None
                    self._last_action = "Reconnect budget exhausted; acknowledge after cause is resolved"
                else:
                    self.state = "reconnect_wait"
                    delay = RECONNECT_DELAYS_SECONDS[self._reconnect_attempts]
                    self._retry_delay_seconds = delay
                    self._retry_at = completed + timedelta(seconds=delay)
                    self._retry_monotonic_deadline = self.monotonic() + delay
            else:
                self.state = "stopped_data"
                self._last_action = "Acknowledge after data cause is resolved"
            if self.state != "reconnect_wait":
                self._stop.set()
            self.store.record_event(
                str(uuid4()), completed.isoformat(), "collector_state_changed", "error",
                "Collector entered a failure state",
                {"state": self.state, "error_class": type(exc).__name__},
            )
        finally:
            self._request_in_flight = False
            if self._paused.is_set() and self.state in {"running", "reconnect_wait"}:
                self.state = "paused"
                self._last_action = "Collection paused"
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
                "configuration_id": self._endpoint_id,
                "reconnect_attempts": self._reconnect_attempts,
                "successful_core_cycles": self._successful_core_cycles,
                "successful_blocks_in_cycle": self._successful_blocks_in_cycle,
                "retry_at": self._retry_at.isoformat() if self._retry_at else None,
                "retry_delay_seconds": self._retry_delay_seconds,
                "retry_block_offset": self._retry_block_offset,
                "next_offset": self._next_offset,
                "next_action": self._last_action,
                "request_in_flight": self._request_in_flight,
            },
            self.now().isoformat(),
        )

    def _persist_state_best_effort(self) -> None:
        try:
            self._persist_state()
        except StorageError:
            pass
