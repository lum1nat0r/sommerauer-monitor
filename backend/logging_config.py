"""Offline-Import und Freigabe ausschließlich für das bestätigte core-Profil."""

from __future__ import annotations

from collections.abc import Mapping
import csv
import io
import re
from typing import Any

from backend.registers import CORE_PROFILE


MAX_CSV_BYTES = 1024 * 1024
MAX_ENTRIES = 5000
MAX_REQUEST_BYTES = 4 * 1024 * 1024

# Codes stammen aus der belegten Zuordnung, Signal-IDs aus dem ausführbaren Profil.
_CORE = {
    "1006": (CORE_PROFILE[0].offset, CORE_PROFILE[0].signal_ids[0], "Kessel_Ist", "°C"),
    "7010": (CORE_PROFILE[1].offset, CORE_PROFILE[1].signal_ids[0], "Betrieb_Tage", "Tage"),
    "7011": (CORE_PROFILE[1].offset + 1, CORE_PROFILE[1].signal_ids[0], "Betrieb_Min", "min"),
    "9000": (CORE_PROFILE[2].offset, CORE_PROFILE[2].signal_ids[0], "Puffer_oben", "°C"),
    "9001": (CORE_PROFILE[2].offset + 1, CORE_PROFILE[2].signal_ids[1], "Puffer_unten", "°C"),
}
_COUNTER_CODES = ("7010", "7011")
_INPUT_FIELDS = {"code", "offset", "name", "record", "unit", "description"}
_ENTRY_FIELDS = _INPUT_FIELDS | {
    "signal_id", "eligible", "blocked_reason", "change", "changed_fields",
}


class LoggingConfigError(ValueError):
    """Ein Import oder Entwurf erfüllt den Konfigurationsvertrag nicht."""


def _text(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise LoggingConfigError(f"{field} muss Text mit {'1' if required else '0'} bis {maximum} Zeichen sein.")
    allowed_controls = "\n\t" if field == "Beschreibung" else ""
    if any((ord(char) < 32 and char not in allowed_controls) or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise LoggingConfigError(f"{field} enthält unzulässige Steuerzeichen.")
    return value


def _code(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9A-Fa-f]{4}", value) is None:
        raise LoggingConfigError("Der interne Code muss aus genau vier Hexzeichen bestehen, z. B. 1006.")
    return value.upper()


def _offset(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 65535:
        raise LoggingConfigError("Der dezimale Offset muss eine ganze Zahl von 0 bis 65535 sein.")
    return value


def normalize_entries(entries: Any) -> list[dict[str, Any]]:
    """Validieren, Freigabe neu berechnen und eine unabhängige kanonische Liste liefern."""
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise LoggingConfigError(f"Die Registerliste muss eine Liste mit höchstens {MAX_ENTRIES} Einträgen sein.")
    result = []
    seen = set()
    offsets = {}
    for raw in entries:
        if not isinstance(raw, Mapping) or set(raw) - _ENTRY_FIELDS or not _INPUT_FIELDS <= set(raw):
            raise LoggingConfigError("Jeder Registereintrag benötigt Code, Offset, Name, Aufzeichnung, Einheit und Beschreibung; unbekannte Felder sind nicht erlaubt.")
        code = _code(raw["code"])
        if code in seen:
            raise LoggingConfigError(f"Code {code} ist mehrfach vorhanden. Auch identische doppelte Einträge sind nicht erlaubt.")
        seen.add(code)
        offset = _offset(raw["offset"])
        if offset in offsets:
            raise LoggingConfigError(f"Offset {offset} ist mehrfach zugeordnet ({offsets[offset]} und {code}); jeder Offset darf nur einmal vorkommen.")
        offsets[offset] = code
        if type(raw["record"]) is not bool:
            raise LoggingConfigError(f"Die Aufzeichnung für {code} muss wahr oder falsch sein.")
        definition = _CORE.get(code)
        signal_id = definition[1] if definition else None
        if "signal_id" in raw and raw["signal_id"] != signal_id:
            raise LoggingConfigError(f"Die Signalzuordnung für {code} ist nicht erlaubt; nur das bestätigte core-Profil ist verfügbar.")
        result.append({
            "code": code,
            "offset": offset,
            "name": _text(raw["name"], "Name", 200, required=True),
            "record": raw["record"],
            "unit": _text(raw["unit"], "Einheit", 40),
            "description": _text(raw["description"], "Beschreibung", 2000),
            "signal_id": signal_id,
            "eligible": False,
            "blocked_reason": None,
            "change": "unchanged",
            "changed_fields": [],
        })
    by_code = {entry["code"]: entry for entry in result}
    counter_complete = all(
        code in by_code and by_code[code]["offset"] == _CORE[code][0]
        for code in _COUNTER_CODES
    )
    for entry in result:
        definition = _CORE.get(entry["code"])
        if definition is None:
            reason = "Kein bestätigter Decoder im core-Profil vorhanden."
        elif entry["offset"] != definition[0]:
            reason = f"Offset weicht von der bestätigten core-Zuordnung ({definition[0]}) ab."
        elif entry["code"] in _COUNTER_CODES and not counter_complete:
            reason = "Betriebszähler benötigt 7010 und 7011 gemeinsam an den bestätigten Offsets 28688 und 28689."
        else:
            reason = None
        entry["eligible"] = reason is None
        entry["blocked_reason"] = reason
        if entry["record"] and reason is not None:
            raise LoggingConfigError(f"{entry['code']} kann nicht aufgezeichnet werden: {reason}")
    if counter_complete and by_code["7010"]["record"] != by_code["7011"]["record"]:
        raise LoggingConfigError("7010 und 7011 müssen für den Betriebszähler gemeinsam ein- oder ausgeschaltet werden.")
    return sorted(result, key=lambda entry: entry["code"])


def default_entries() -> list[dict[str, Any]]:
    """Ohne Speicherung bleibt die bisherige Aufzeichnung aller Kernregister erhalten."""
    return normalize_entries([
        {"code": code, "offset": definition[0], "name": definition[2],
         "record": True, "unit": definition[3], "description": ""}
        for code, definition in _CORE.items()
    ])


def parse_csv(csv_text: Any) -> list[dict[str, Any]]:
    if not isinstance(csv_text, str):
        raise LoggingConfigError("Der CSV-Inhalt muss Text sein.")
    try:
        size = len(csv_text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise LoggingConfigError("Der CSV-Inhalt enthält ungültige Unicode-Zeichen.") from exc
    if size > MAX_CSV_BYTES:
        raise LoggingConfigError("Die CSV-Datei darf höchstens 1 MiB groß sein.")
    reader = csv.reader(io.StringIO(csv_text.removeprefix("\ufeff"), newline=""), delimiter=";", strict=True)
    result = []
    by_code = {}
    offsets = {}
    try:
        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 3:
                raise LoggingConfigError(f"CSV-Zeile {reader.line_num}: Erwartet wird Name;dezimaler Offset;interner Hexcode ohne Kopfzeile.")
            name, raw_offset, raw_code = (value.strip() for value in row)
            try:
                code = _code(raw_code)
                if re.fullmatch(r"[0-9]+", raw_offset) is None:
                    raise LoggingConfigError("Der Offset muss dezimal angegeben werden.")
                decimal = raw_offset.lstrip("0") or "0"
                if len(decimal) > 5:
                    raise LoggingConfigError("Der dezimale Offset muss zwischen 0 und 65535 liegen.")
                offset = _offset(int(decimal))
                name = _text(name, "Name", 200, required=True)
            except LoggingConfigError as exc:
                raise LoggingConfigError(f"CSV-Zeile {reader.line_num}: {exc}") from exc
            entry = {"code": code, "offset": offset, "name": name}
            if code in by_code:
                kind = "Identischer doppelter" if by_code[code] == entry else "Widersprüchlicher doppelter"
                raise LoggingConfigError(f"CSV-Zeile {reader.line_num}: {kind} Eintrag für Code {code}; jeder Code darf nur einmal vorkommen.")
            if offset in offsets:
                raise LoggingConfigError(f"CSV-Zeile {reader.line_num}: Offset {offset} ist mehrfach zugeordnet ({offsets[offset]} und {code}).")
            offsets[offset] = code
            by_code[code] = entry
            result.append(entry)
            if len(result) > MAX_ENTRIES:
                raise LoggingConfigError(f"Eine CSV-Datei darf höchstens {MAX_ENTRIES} Register enthalten.")
    except csv.Error as exc:
        raise LoggingConfigError(f"CSV-Zeile {reader.line_num}: Ungültige CSV-Syntax ({exc}).") from exc
    if not result:
        raise LoggingConfigError("Die CSV-Datei enthält keine Registerzeilen.")
    return result


def merge_csv(entries: list[dict[str, Any]], csv_text: str) -> list[dict[str, Any]]:
    """Inkrementeller Entwurf: Fehlendes bleibt erhalten; Import ändert keine Speicherung."""
    current = normalize_entries(entries)
    previous_by_code = {entry["code"]: entry for entry in current}
    by_code = {code: dict(entry) for code, entry in previous_by_code.items()}
    for imported in parse_csv(csv_text):
        code = imported["code"]
        previous = previous_by_code.get(code)
        if previous is None:
            by_code[code] = {**imported, "record": False, "unit": "", "description": ""}
        else:
            by_code[code].update(imported)
            if imported["offset"] != previous["offset"]:
                by_code[code]["record"] = False
    # Jede geänderte Wortzuordnung deaktiviert den gesamten Mehrwortzähler.
    if any(
        code in by_code and (code not in previous_by_code
        or by_code[code]["offset"] != previous_by_code[code]["offset"])
        for code in _COUNTER_CODES
    ):
        for code in _COUNTER_CODES:
            if code in by_code:
                by_code[code]["record"] = False
    merged = normalize_entries(list(by_code.values()))
    for entry in merged:
        previous = previous_by_code.get(entry["code"])
        fields = ["name", "offset"] if previous is None else [
            field for field in ("name", "offset") if entry[field] != previous[field]
        ]
        entry["change"] = "new" if previous is None else "changed" if fields else "unchanged"
        entry["changed_fields"] = fields
    return merged


def prepare_save(entries: Any, current_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PUT erneut prüfen; Einträge dürfen weder verschwinden noch Decoder erfinden."""
    normalized = normalize_entries(entries)
    current = {entry["code"]: entry for entry in normalize_entries(current_entries)}
    by_code = {entry["code"]: entry for entry in normalized}
    missing = current.keys() - by_code.keys()
    if missing:
        raise LoggingConfigError(f"Register dürfen nicht gelöscht werden. Fehlende Codes: {', '.join(sorted(missing))}.")
    return normalized


def selected_signal_ids(entries: list[dict[str, Any]]) -> frozenset[str]:
    """Nur erneut validierte, freigegebene Signale dürfen Messungen erzeugen."""
    return frozenset(
        entry["signal_id"] for entry in normalize_entries(entries)
        if entry["record"] and entry["eligible"] and entry["signal_id"] is not None
    )
