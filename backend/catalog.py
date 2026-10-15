"""Unveränderliche Diagnoseauswahl; unabhängig vom aktiven Kernpolling."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from types import MappingProxyType
from typing import Any, Literal

from backend.registers import CORE_PROFILE


@dataclass(frozen=True, slots=True)
class CatalogReadBlock:
    offset: int
    count: int


_CORE_BLOCKS = tuple(CatalogReadBlock(block.offset, block.count) for block in CORE_PROFILE)
_CORE_BY_WORD = MappingProxyType({
    offset: block
    for block in _CORE_BLOCKS
    for offset in range(block.offset, block.offset + block.count)
})
_REGISTER_ID = re.compile(r"register:(0|[1-9][0-9]{0,4})", flags=re.ASCII)


class CatalogUnavailable(ValueError):
    """Die Paketressource erlaubt keine Diagnoseplanung."""

    code = "catalog_unavailable"

    def __init__(self) -> None:
        super().__init__("Registerkatalog nicht verfügbar oder ungültig.")


class CatalogSelectionError(ValueError):
    """Die Auswahl ergibt keinen erlaubten endlichen Diagnoseplan."""

    code = "invalid_register_selection"

    def __init__(self) -> None:
        super().__init__("Auswahl muss 1 bis 3 gültige Katalogblöcke ergeben.")


def _freeze(value: Any) -> Any:
    """Auch unbekannte, verschachtelte Belegfelder verlustfrei einfrieren."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    # Originalfelder einschließlich optionaler und künftig ergänzter Belege.
    fields: Mapping[str, Any]

    @property
    def offset_zero_based(self) -> int:
        return self.fields["offset_zero_based"]

    @property
    def register_id(self) -> str:
        return f"register:{self.offset_zero_based}"

    @property
    def sl_code_hex(self) -> str:
        return self.fields["sl_code_hex"]

    @property
    def csv_label(self) -> str:
        return self.fields["csv_label"]

    @property
    def register_words(self) -> int:
        return self.fields["register_words"]

    @property
    def in_user_reported_imported_profile(self) -> bool:
        return self.fields["in_user_reported_imported_profile"]

    @property
    def evidence_status(self) -> str:
        return self.fields["evidence_status"]

    @property
    def meaning(self) -> str | None:
        return self.fields.get("meaning")

    @property
    def unit(self) -> str | None:
        return self.fields.get("unit") if self.read_support == "confirmed_core" else None

    @property
    def decoding(self) -> str | None:
        return self.fields.get("decoding")

    @property
    def polling_enabled(self) -> bool | None:
        return self.fields.get("polling_enabled")

    @property
    def read_support(self) -> Literal["confirmed_core", "documented_raw"]:
        return "confirmed_core" if self.offset_zero_based in _CORE_BY_WORD else "documented_raw"

    @property
    def write_support(self) -> Literal["unknown"]:
        return "unknown"

    @property
    def decoded_value(self) -> None:
        # Der Katalog enthält keine Messung, auch nicht für Kernregister.
        return None


@dataclass(frozen=True, slots=True)
class RegisterCatalog:
    entries: Mapping[int, CatalogEntry]
    sha256: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ControlCandidate:
    candidate_id: str
    label: str
    sl_code_hex: str
    potential_offset: int
    source: str = "docs/START_RUECKFALL.md"
    read_block: None = None
    write_support: Literal["unknown"] = "unknown"
    limitation: str = (
        "Unbelegter Stellweg; Kodierung und autonomer Rückfall bei Host-/Netzausfall "
        "ungeklärt. Ein Timer ersetzt keinen Nachweis."
    )


CONTROL_CANDIDATES = MappingProxyType({
    "control:buffer.start": ControlCandidate("control:buffer.start", "START", "9040", 36928),
    "control:buffer.target": ControlCandidate("control:buffer.target", "SOLL", "9020", 36896),
})


def _integer(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _validate(document: Any, sha256: str) -> RegisterCatalog:
    if not isinstance(document, dict):
        raise ValueError
    for field, expected in (("schema_version", 1), ("read_function", 3), ("unit_id", 255)):
        if not _integer(document.get(field), expected, expected):
            raise ValueError
    registers = document.get("registers")
    if not isinstance(registers, list) or not registers:
        raise ValueError

    entries = {}
    for record in registers:
        if not isinstance(record, dict):
            raise ValueError
        offset = record.get("offset_zero_based")
        if not _integer(offset, 0, 65535) or offset in entries:
            raise ValueError
        if not _integer(record.get("register_words"), 1, 1):
            raise ValueError
        code = record.get("sl_code_hex")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9a-fA-F]+", code):
            raise ValueError
        if int(code, 16) != offset:
            raise ValueError
        for field in ("csv_label", "evidence_status"):
            if not isinstance(record.get(field), str) or not record[field]:
                raise ValueError
        if type(record.get("in_user_reported_imported_profile")) is not bool:
            raise ValueError
        for field in ("meaning", "unit", "decoding"):
            if record.get(field) is not None and not isinstance(record[field], str):
                raise ValueError
        if "polling_enabled" in record and type(record["polling_enabled"]) is not bool:
            raise ValueError
        entries[offset] = CatalogEntry(_freeze(record))

    if not _CORE_BY_WORD.keys() <= entries.keys():
        raise ValueError
    known_blocks = document.get("known_read_blocks")
    if not isinstance(known_blocks, list):
        raise ValueError
    blocks = []
    for block in known_blocks:
        if not isinstance(block, dict):
            raise ValueError
        if not _integer(block.get("offset"), 0, 65535):
            raise ValueError
        if not _integer(block.get("count"), 1, 2):
            raise ValueError
        blocks.append(CatalogReadBlock(block["offset"], block["count"]))
    if len(blocks) != len(_CORE_BLOCKS) or set(blocks) != set(_CORE_BLOCKS):
        raise ValueError
    return RegisterCatalog(
        entries=MappingProxyType(entries),
        sha256=sha256,
        metadata=_freeze({key: value for key, value in document.items() if key != "registers"}),
    )


@cache
def _catalog_snapshot() -> RegisterCatalog | None:
    # Auch ein fehlgeschlagener Snapshot bleibt bis zum Prozessneustart gesperrt.
    try:
        raw = resources.files("backend").joinpath("resources/register_catalog.json").read_bytes()
        return _validate(json.loads(raw), hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, TypeError, RecursionError):
        return None


def load_catalog() -> RegisterCatalog:
    """Erst bei Diagnosebedarf laden; keine Quelle/Datei nachträglich nachladen."""
    catalog = _catalog_snapshot()
    if catalog is None:
        raise CatalogUnavailable()
    return catalog


def build_read_blocks(register_ids: list[str]) -> tuple[CatalogReadBlock, ...]:
    """Nur Katalog-IDs in exakte Kernblöcke oder einzelne Rohworte auflösen."""
    catalog = load_catalog()
    if not isinstance(register_ids, list):
        raise CatalogSelectionError()
    blocks = set()
    for register_id in register_ids:
        match = _REGISTER_ID.fullmatch(register_id) if isinstance(register_id, str) else None
        if match is None:
            raise CatalogSelectionError()
        offset = int(match[1])
        if offset not in catalog.entries:
            raise CatalogSelectionError()
        blocks.add(_CORE_BY_WORD[offset] if offset in _CORE_BY_WORD else CatalogReadBlock(offset, 1))
    if not 1 <= len(blocks) <= 3:
        raise CatalogSelectionError()
    return tuple(sorted(blocks, key=lambda block: block.offset))
