"""CSV-Auswahl für explizit quellengeprüfte Leseregister, ohne automatische Aktivierung."""

from __future__ import annotations

from collections.abc import Mapping
import csv
import io
import json
import re
from typing import Any

from backend.registers import REGISTER_DEFINITIONS, SIGNAL_DEFINITIONS


MAX_CSV_BYTES = 1024 * 1024
MAX_ENTRIES = 5000
MAX_REQUEST_BYTES = 4 * 1024 * 1024
# Platz für die lokale Revision und die JSON-Anfragehülle beim Wiederimport.
MAX_TRANSFER_BYTES = MAX_REQUEST_BYTES - 1024

_CORE_CODES = ("1006", "7010", "7011", "9000", "9001")
_COUNTER_GROUPS = (("7010", "7011"), ("7012", "7013"))
_TRANSFER_FIELDS = ("code", "offset", "name", "record", "unit", "description")
_INPUT_FIELDS = set(_TRANSFER_FIELDS)
_ENTRY_FIELDS = _INPUT_FIELDS | {
    "signal_id", "eligible", "blocked_reason", "change", "changed_fields",
    "kind", "live_confirmed", "read_to_clear", "decoder", "information",
    "label", "verification_status", "module_status",
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
        definition = REGISTER_DEFINITIONS.get(code)
        signal_id = definition["signal_id"] if definition else None
        # Früher unbekannte gespeicherte CSV-Zeilen hatten noch keine Signal-ID.
        if raw.get("signal_id") not in (None, signal_id):
            raise LoggingConfigError(f"Die Signalzuordnung für {code} stimmt nicht mit dem geprüften Leseprofil überein.")
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
            "kind": definition["kind"] if definition else "unknown",
            "live_confirmed": definition["live_confirmed"] if definition else False,
            "label": SIGNAL_DEFINITIONS[signal_id]["label"] if definition else None,
            "verification_status": definition["verification_status"] if definition else "unknown",
            "module_status": definition["module_status"] if definition else "unknown",
            "read_to_clear": definition["read_to_clear"] if definition else False,
            "decoder": definition["decoder"] if definition else None,
            "information": definition["description"] if definition else "Keine geprüfte Registerdefinition vorhanden.",
        })
    by_code = {entry["code"]: entry for entry in result}
    complete_groups = {
        group: all(
            code in by_code and by_code[code]["offset"] == REGISTER_DEFINITIONS[code]["offset"]
            for code in group
        )
        for group in _COUNTER_GROUPS
    }
    for entry in result:
        definition = REGISTER_DEFINITIONS.get(entry["code"])
        group = next((group for group in _COUNTER_GROUPS if entry["code"] in group), None)
        if definition is None:
            reason = "Kein quellengeprüfter Decoder für diesen Code vorhanden."
        elif entry["offset"] != definition["offset"]:
            reason = f"Offset weicht von der bestätigten core-Zuordnung bzw. quellengeprüften Zuordnung ({definition['offset']}) ab."
        elif group is not None and not complete_groups[group]:
            reason = f"Zähler benötigt {' und '.join(group)} gemeinsam an den zugeordneten Offsets."
        else:
            reason = None
        entry["eligible"] = reason is None
        entry["blocked_reason"] = reason
        if entry["record"] and reason is not None:
            raise LoggingConfigError(f"{entry['code']} kann nicht aufgezeichnet werden: {reason}")
    for group, complete in complete_groups.items():
        if complete and by_code[group[0]]["record"] != by_code[group[1]]["record"]:
            raise LoggingConfigError(f"{' und '.join(group)} müssen für den Zähler gemeinsam ein- oder ausgeschaltet werden.")
    return sorted(result, key=lambda entry: entry["code"])


def default_entries() -> list[dict[str, Any]]:
    """Ohne Speicherung bleibt die bisherige Aufzeichnung aller Kernregister erhalten."""
    return normalize_entries([
        {"code": code, "offset": REGISTER_DEFINITIONS[code]["offset"],
         "name": REGISTER_DEFINITIONS[code]["name"], "record": True,
         "unit": "Tage" if code == "7010" else REGISTER_DEFINITIONS[code]["unit"], "description": ""}
        for code in _CORE_CODES
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
    imported_rows = parse_csv(csv_text)
    imported_codes = {row["code"] for row in imported_rows}
    for imported in imported_rows:
        code = imported["code"]
        previous = previous_by_code.get(code)
        if previous is None:
            by_code[code] = {**imported, "record": False, "unit": "", "description": ""}
        else:
            by_code[code].update(imported)
            if imported["offset"] != previous["offset"]:
                by_code[code]["record"] = False
    # Jede geänderte Wortzuordnung deaktiviert den gesamten Mehrwortzähler.
    for group in _COUNTER_GROUPS:
        if any(
            code in by_code and (code not in previous_by_code
            or by_code[code]["offset"] != previous_by_code[code]["offset"])
            for code in group
        ):
            for code in group:
                if code in by_code:
                    by_code[code]["record"] = False
    merged = normalize_entries(list(by_code.values()))
    for entry in merged:
        if entry["code"] in imported_codes:
            entry["record"] = entry["eligible"]
    # Ein hochgeladenes Zählerwort wählt das vollständige, zugeordnete Paar.
    for group in _COUNTER_GROUPS:
        if imported_codes.intersection(group):
            pair = [entry for entry in merged if entry["code"] in group]
            selected = len(pair) == len(group) and all(entry["eligible"] for entry in pair)
            for entry in pair:
                entry["record"] = selected
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


def export_configuration(entries: Any) -> bytes:
    """Nur gespeicherte Eingabefelder übertragen; Freigaben bleiben Sache des Ziels."""
    document = {
        "version": 1,
        "entries": [
            {field: entry[field] for field in _TRANSFER_FIELDS}
            for entry in normalize_entries(entries)
        ],
    }
    content = (json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(content) > MAX_TRANSFER_BYTES:
        raise LoggingConfigError("Die JSON-Aufzeichnungskonfiguration ist zu groß (maximal 4 MiB abzüglich 1 KiB Anfragehülle).")
    return content


def import_configuration(document: Any, current_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exakte Dateiauswahl als Entwurf; nur lokal vorhandene Zeilen bleiben abgewählt."""
    if not isinstance(document, dict) or set(document) != {"version", "entries"}:
        raise LoggingConfigError("Die JSON-Datei benötigt genau version und entries; andere Einstellungen sind nicht übertragbar.")
    if type(document["version"]) is not int or document["version"] != 1:
        raise LoggingConfigError("Die JSON-Datei benötigt die ganzzahlige Formatversion 1.")
    entries = document["entries"]
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) or set(entry) != _INPUT_FIELDS for entry in entries
    ):
        raise LoggingConfigError("JSON-Register benötigen ausschließlich code, offset, name, record, unit und description.")
    imported = normalize_entries(entries)
    export_configuration(imported)
    previous = {entry["code"]: entry for entry in normalize_entries(current_entries)}
    by_code = {code: {**entry, "record": False} for code, entry in previous.items()}
    by_code.update({entry["code"]: entry for entry in imported})
    draft = prepare_save(list(by_code.values()), current_entries)
    for entry in draft:
        old = previous.get(entry["code"])
        fields = list(_TRANSFER_FIELDS) if old is None else [
            field for field in _TRANSFER_FIELDS if entry[field] != old[field]
        ]
        entry["change"] = "new" if old is None else "changed" if fields else "unchanged"
        entry["changed_fields"] = fields
    return draft


def selected_signal_ids(entries: list[dict[str, Any]]) -> frozenset[str]:
    """Nur erneut validierte, freigegebene Signale dürfen Messungen erzeugen."""
    return frozenset(
        entry["signal_id"] for entry in normalize_entries(entries)
        if entry["record"] and entry["eligible"] and entry["signal_id"] is not None
    )
