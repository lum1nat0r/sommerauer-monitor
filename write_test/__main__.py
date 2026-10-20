"""Begrenzter START/SOLL-Test mit privatem Plan und dauerhaftem Journal."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sqlite3
import struct
import time
from contextlib import contextmanager


OFFSETS = {"9040": 36928, "9020": 36896}
ENCODING_SOURCE = "9965d1d31300a0e96e60a75730d23628632b161679d5c5356462edeca3496323"
TEMPLATE = {
    "target_ip": None,
    "port": 502,
    "unit": 255,
    "hold_seconds": 10,
    "encoding_source": ENCODING_SOURCE,
    "encoding_confirmed": False,
    "registers": [
        {
            "code": code,
            "original_c": None,
            "test_c": None,
        }
        for code in OFFSETS
    ],
}


class ToolError(ValueError):
    """Öffentlich ausgebbare Meldung ohne private Ziel- oder Pfadangaben."""


def integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def write_word(temperature: int) -> int:
    """Inverse des statisch geprüften Dezimaltext→Hex-Pfads, kein Gerätebeweis."""
    if not integer(temperature, 10, 90):
        raise ToolError("Temperaturen müssen ganze Zahlen von 10 bis 90 °C sein.")
    digits = format(temperature, "X")
    if any(character not in "0123456789" for character in digits):
        raise ToolError(
            f"{temperature} °C ist im geprüften FC06-Pfad nicht darstellbar. "
            "Kein Versuch: auch der Rückstellwert muss darstellbar sein."
        )
    return int(digits, 10)


def validate(plan: dict, *, live: bool) -> None:
    if not isinstance(plan, dict) or plan.keys() != TEMPLATE.keys():
        raise ToolError("Planfelder stimmen nicht mit der Vorlage überein.")
    if live:
        try:
            target = ipaddress.ip_address(plan["target_ip"])
        except (ValueError, TypeError) as error:
            raise ToolError(
                "Numerische Zieladresse aus privater Konfiguration erforderlich."
            ) from error
        if target.is_multicast or target.is_unspecified or str(target) == "255.255.255.255":
            raise ToolError("Kein Multicast-, Broadcast- oder unbestimmtes Ziel erlaubt.")
        if plan["encoding_confirmed"] is not True:
            raise ToolError(
                "Übereinstimmung der Geräteversion mit dem geprüften Export bestätigen."
            )
    if plan["encoding_source"] != ENCODING_SOURCE:
        raise ToolError("Unbekanntes Schreibprofil; kein Standard-Encoding als Ausweichweg.")
    if not integer(plan["port"], 1, 65535) or type(plan["unit"]) is not int or plan["unit"] != 255:
        raise ToolError("Port 1–65535 und ausschließlich Unit 255 erforderlich.")
    if not integer(plan["hold_seconds"], 0, 60):
        raise ToolError("Testdauer muss eine ganze Zahl von 0 bis 60 Sekunden sein.")
    entries = plan["registers"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 2:
        raise ToolError("Genau ein oder zwei Kandidaten erforderlich.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != TEMPLATE["registers"][0].keys():
            raise ToolError("Ungültige Registerfelder.")
        code = entry["code"]
        if not isinstance(code, str) or code not in OFFSETS or code in seen:
            raise ToolError("Nur eindeutige START-/SOLL-Kandidaten 9040/9020 erlaubt.")
        seen.add(code)
        if not all(integer(entry[key], 10, 90) for key in ("original_c", "test_c")):
            raise ToolError("Ausgangs- und Testtemperatur müssen ganze Zahlen 10–90 °C sein.")
        write_word(entry["original_c"])
        write_word(entry["test_c"])


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


class TcpTransport:
    """FC03/FC06, Unit 255, nur ein Wort der beiden Kandidaten, keine Retries."""

    def __init__(self, plan: dict):
        validate(plan, live=True)
        self.address = (plan["target_ip"], plan["port"])
        self.transaction = 0

    def exchange(self, code: str, function: int, value: int) -> int:
        if code not in OFFSETS or function not in (3, 6):
            raise ToolError("Nicht zugelassene Anfrage.")
        if not integer(value, 0, 65535) or (function == 3 and value != 1):
            raise ToolError("Nur ein Wort pro Anfrage.")
        self.transaction = (self.transaction + 1) & 65535
        pdu = struct.pack(">BHH", function, OFFSETS[code], value)
        request = struct.pack(">HHHB", self.transaction, 0, 6, 255) + pdu
        deadline = time.monotonic() + 3

        def remaining() -> float:
            result = deadline - time.monotonic()
            if result <= 0:
                raise TimeoutError("Gesamtdeadline überschritten.")
            return result

        with socket.create_connection(self.address, timeout=remaining()) as connection:
            connection.settimeout(remaining())
            connection.sendall(request)

            def receive(size: int) -> bytes:
                data = bytearray()
                while len(data) < size:
                    connection.settimeout(remaining())
                    chunk = connection.recv(size - len(data))
                    if not chunk:
                        raise ToolError("Unvollständige Antwort.")
                    data.extend(chunk)
                return bytes(data)

            transaction, protocol, length, unit = struct.unpack(">HHHB", receive(7))
            if transaction != self.transaction or protocol != 0 or unit != 255:
                raise ToolError("MBAP-Antwort passt nicht zur Anfrage.")
            expected_length = 5 if function == 3 else 6
            if length not in (3, expected_length):
                raise ToolError("Ungültige Antwortlänge.")
            response = receive(length - 1)
        if response[0] == function | 128 and len(response) == 2:
            raise ToolError(f"Modbus-Ablehnung {response[1]}.")
        if function == 3:
            if len(response) != 4 or response[:2] != b"\x03\x02":
                raise ToolError("Ungültige FC03-Antwort.")
            return int.from_bytes(response[2:], "big")
        if response != pdu:
            raise ToolError("FC06-Echo passt nicht; Ausgang ungewiss.")
        return value


class MemoryTransport:
    """Synthetisches Modell des statisch geprüften Pfads, keine laufende Firmware."""

    def __init__(self, plan: dict, fault: str = "none"):
        self.words = {e["code"]: e["original_c"] for e in plan["registers"]}
        self.fault = fault
        self.writes = 0

    def exchange(self, code: str, function: int, value: int) -> int:
        if function == 3:
            if self.fault == "readback-mismatch" and self.writes == 1:
                return 0
            return self.words[code]
        if self.fault == "reject-write" and self.writes == 0:
            raise ToolError("Synthetische Schreibablehnung.")
        if self.fault == "restore-failure" and self.writes == 1:
            raise OSError("Synthetischer Rückstellfehler.")
        decoded = int(str(value), 16)
        if 10 <= decoded <= 90:
            self.words[code] = decoded
        self.writes += 1
        if self.fault == "lost-ack" and self.writes == 1:
            raise TimeoutError("Synthetisch verlorene Bestätigung.")
        return value


class Journal:
    """Jede Anfrage vor dem Versand reservieren; unterbrochene Läufe nie fortsetzen."""

    def __init__(self, path: Path):
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        if existed:
            try:
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                record = self.db.execute("SELECT id FROM run WHERE id=1").fetchone()
                if version != 1 or record is None:
                    raise ToolError("Journalzustand unvollständig; kein automatischer Neubeginn.")
            except BaseException:
                self.db.close()
                raise
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS run (
                id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT, mode TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, code TEXT, action TEXT, requested INTEGER,
                observed INTEGER, status TEXT
            );
            CREATE TABLE IF NOT EXISTS restore (
                code TEXT PRIMARY KEY, original_c INTEGER, restore_write_word INTEGER
            );
        """)
        if not existed:
            self.db.execute("PRAGMA user_version=1")

    def start(self, plan: dict, mode: str) -> None:
        try:
            self.db.execute(
                "INSERT INTO run VALUES (1, ?, ?, 'running')", (fingerprint(plan), mode)
            )
            self.db.commit()
        except sqlite3.IntegrityError as error:
            raise ToolError(
                "Journal enthält bereits einen Lauf; kein Neustart/Retry erlaubt."
            ) from error

    def reserve(self, code: str, action: str, value: int) -> int:
        count = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
        if count >= 12:
            raise ToolError("Anfragebudget erschöpft.")
        cursor = self.db.execute(
            "INSERT INTO events(code, action, requested, status) VALUES (?, ?, ?, 'unknown')",
            (code, action, value),
        )
        self.db.commit()
        return cursor.lastrowid

    def answered(self, identifier: int, value: int, valid: bool) -> None:
        self.db.execute(
            "UPDATE events SET observed=?, status=? WHERE id=?",
            (value, "ok" if valid else "mismatch", identifier),
        )
        self.db.commit()

    def remember_restore(self, entry: dict) -> None:
        self.db.execute(
            "INSERT INTO restore VALUES (?, ?, ?)",
            (entry["code"], entry["original_c"], entry["restore_write_word"]),
        )
        self.db.commit()

    def restored(self, code: str) -> None:
        self.db.execute("DELETE FROM restore WHERE code=?", (code,))
        self.db.commit()

    def finish(self, status: str) -> None:
        self.db.execute("UPDATE run SET status=? WHERE id=1", (status,))
        self.db.commit()

    def report(self) -> dict:
        run = self.db.execute("SELECT fingerprint, mode, status FROM run WHERE id=1").fetchone()
        events = self.db.execute(
            "SELECT id, code, action, requested, observed, status FROM events ORDER BY id"
        ).fetchall()
        restore = self.db.execute(
            "SELECT code, original_c, restore_write_word FROM restore ORDER BY code"
        ).fetchall()
        return {"run": run, "events": events, "manual_review_restore_values": restore}

    def close(self) -> None:
        self.db.close()


def run(plan: dict, transport, journal: Journal, *, mode: str, wait=time.sleep) -> None:
    validate(plan, live=mode == "live")
    journal.start(plan, mode)

    def request(entry: dict, action: str, value: int, expected: int, function: int) -> None:
        identifier = journal.reserve(entry["code"], action, value)
        observed = transport.exchange(entry["code"], function, value)
        journal.answered(identifier, observed, observed == expected)
        if observed != expected:
            raise ToolError("Rücklesen widersprüchlich; keine weiteren Anfragen.")

    try:
        for entry in plan["registers"]:
            entry = dict(
                entry,
                test_write_word=write_word(entry["test_c"]),
                restore_write_word=write_word(entry["original_c"]),
            )
            original = entry["original_c"]
            target = entry["test_c"]
            request(entry, "read-before", 1, original, 3)
            if original == target:
                continue
            journal.remember_restore(entry)
            request(entry, "write-test", entry["test_write_word"], entry["test_write_word"], 6)
            request(entry, "verify-test", 1, target, 3)
            # Monotone Dauer ab Rücklesebestätigung; keine Polling-/Heartbeat-Anfragen.
            wait(plan["hold_seconds"])
            # Eine Bedienänderung am Touch nicht blind mit dem alten Wert überschreiben.
            request(entry, "check-before-restore", 1, target, 3)
            request(
                entry, "write-restore", entry["restore_write_word"], entry["restore_write_word"], 6
            )
            request(entry, "verify-restore", 1, original, 3)
            journal.restored(entry["code"])
        journal.finish("completed")
    except BaseException:
        journal.finish("stopped-review-required")
        raise


@contextmanager
def exclusive(directory: Path):
    """Lokale Werkzeuginstanzen koordinieren; fremde Leser vorher manuell stoppen."""
    import fcntl

    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".write-test.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("template", "review", "simulate", "execute", "status"))
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--approve", help="SHA256 des konkret freigegebenen Plans, nur für execute")
    parser.add_argument(
        "--fault",
        choices=("none", "reject-write", "lost-ack", "readback-mismatch", "restore-failure"),
        default="none",
        help="Nur für simulate: synthetischer Fehler am ersten geänderten Kandidaten",
    )
    args = parser.parse_args(argv)
    if args.command != "simulate" and args.fault != "none":
        parser.error("Fehlersimulation nur mit simulate erlaubt.")
    if args.command == "template":
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        if args.journal is None or not args.journal.is_file():
            parser.error("Vorhandenes --journal erforderlich.")
        journal = Journal(args.journal)
        try:
            print(json.dumps(journal.report(), ensure_ascii=False, indent=2))
        finally:
            journal.close()
        return 0
    if args.plan is None:
        parser.error("--plan erforderlich.")
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        validate(plan, live=args.command in ("review", "execute"))
        digest = fingerprint(plan)
        if args.command == "review":
            print(f"Plan-SHA256: {digest}")
            print(
                "FC03/FC06, Unit 255, ein Register, 3 s Deadline, "
                f"maximal {6 * len(plan['registers'])} Anfragen."
            )
            for entry in plan["registers"]:
                print(
                    f"{entry['code']}: {entry['original_c']} → {entry['test_c']} °C; "
                    f"Rückstellung nach {plan['hold_seconds']} s Wartezeit auf "
                    f"{entry['original_c']} °C; Schreibwörter "
                    f"Test={write_word(entry['test_c'])}, Rückstellung={write_word(entry['original_c'])}."
                )
            print("Andere Leser vorher stoppen. Manuelle Rückstellung am Touch bereithalten.")
            print("Kein garantierter Rückfall bei Host-/Netzausfall. Keine Anfrage ausgeführt.")
            return 0
        if args.journal is None:
            parser.error("--journal erforderlich, getrennte dauerhafte Datei pro Lauf.")
        if args.command == "execute" and args.approve != digest:
            raise ToolError("Konkrete Planfreigabe fehlt oder Plan wurde verändert.")
        transport = (
            TcpTransport(plan) if args.command == "execute" else MemoryTransport(plan, args.fault)
        )
        with exclusive(args.journal.parent):
            journal = Journal(args.journal)
            try:
                run(
                    plan,
                    transport,
                    journal,
                    mode="live" if args.command == "execute" else "synthetic",
                )
                print(json.dumps(journal.report(), ensure_ascii=False, indent=2))
            finally:
                journal.close()
    except ToolError as error:
        print(f"Stopp: {error} Journal lokal prüfen; kein automatischer Folgeversuch.")
        return 1
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        # Rohe Fehler können private Ziele/Pfade enthalten; nur lokale Journalprüfung anbieten.
        print(
            f"Stopp ({type(error).__name__}). Journal und Plan lokal prüfen; "
            "bei möglicher Änderung am Touch kontrollieren. Kein automatischer Folgeversuch."
        )
        return 1
    except KeyboardInterrupt:
        print("Gestoppt. Mögliche Änderung am Touch prüfen; kein automatischer Folgeversuch.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
