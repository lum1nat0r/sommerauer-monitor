"""Gemeinsamer exklusiver Gerätebesitz für Kernsammler und Diagnose."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class DeviceOwnershipError(RuntimeError):
    """Ein anderer Besitzer hält die gemeinsame Sperre dieses Datenvolumens."""


class DeviceLock:
    """Plattformübergreifende OS-Sperre für die gesamte Lebenszeit eines Lesers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Any = None

    def acquire(self) -> None:
        if self._file is not None:
            raise DeviceOwnershipError("device lock is held by another reader")
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
            raise DeviceOwnershipError("device lock is held by another process") from exc
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
