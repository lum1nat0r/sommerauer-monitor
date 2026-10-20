"""Ausschließlich synthetische Prüfungen, auch für den TCP-Adapter ohne Netzwerk."""

from contextlib import closing, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import socketserver
import struct
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from write_test.__main__ import (
    Journal,
    MemoryTransport,
    TEMPLATE,
    TcpTransport,
    fingerprint,
    exclusive,
    main,
    run,
    validate,
    write_word,
)


def synthetic_plan():
    plan = deepcopy(TEMPLATE)
    plan.update(
        target_ip="127.0.0.1",
        hold_seconds=0,
        encoding_confirmed=True,
    )
    for entry, original, target in zip(plan["registers"], (40, 65), (35, 64)):
        entry.update(
            original_c=original,
            test_c=target,
        )
    return plan


class WriteToolTest(unittest.TestCase):
    def test_codec_matches_complete_reachable_temperature_set(self):
        # Vorwärtsmodell des rekonstruierten Exports, unabhängig vom Invers-Encoder.
        reachable = {
            int(str(word), 16): word for word in range(65536) if 10 <= int(str(word), 16) <= 90
        }
        self.assertEqual(
            set(reachable),
            set(range(16, 26))
            | set(range(32, 42))
            | set(range(48, 58))
            | set(range(64, 74))
            | set(range(80, 90)),
        )
        for temperature in range(10, 91):
            if temperature in reachable:
                self.assertEqual(write_word(temperature), reachable[temperature])
            else:
                with self.assertRaises(ValueError):
                    write_word(temperature)

    def test_unrepresentable_second_restore_prevents_first_register_dispatch(self):
        plan = synthetic_plan()
        plan["registers"][1]["original_c"] = 60
        with TemporaryDirectory() as folder, closing(Journal(Path(folder) / "test.db")) as journal:
            transport = MemoryTransport(plan)
            with patch.object(transport, "exchange") as exchange, self.assertRaises(ValueError):
                run(plan, transport, journal, mode="synthetic")
            exchange.assert_not_called()
            self.assertIsNone(journal.report()["run"])

    def test_parallel_tool_invocations_share_exclusive_directory_lock(self):
        with TemporaryDirectory() as folder, exclusive(Path(folder)):
            with self.assertRaises(BlockingIOError), exclusive(Path(folder)):
                self.fail("Zweiter Client darf den Lock nicht bekommen.")

    def test_restores_both_registers_and_never_replays_a_journal(self):
        plan = synthetic_plan()
        with TemporaryDirectory() as folder, closing(Journal(Path(folder) / "test.db")) as journal:
            transport = MemoryTransport(plan)
            run(plan, transport, journal, mode="synthetic")
            self.assertEqual(transport.words, {"9040": 40, "9020": 65})
            self.assertEqual(journal.report()["run"][2], "completed")
            self.assertEqual(len(journal.report()["events"]), 12)
            with self.assertRaises(ValueError):
                run(plan, transport, journal, mode="synthetic")
            self.assertEqual(len(journal.report()["events"]), 12)

    def test_lost_ack_after_change_keeps_unknown_attempt_and_stops(self):
        plan = synthetic_plan()

        class LostAck(MemoryTransport):
            def exchange(self, code, function, value):
                result = super().exchange(code, function, value)
                if function == 6:
                    raise TimeoutError("synthetic")
                return result

        with TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            transport = LostAck(plan)
            with closing(Journal(path)) as journal:
                with self.assertRaises(TimeoutError):
                    run(plan, transport, journal, mode="synthetic")
                self.assertEqual(transport.words, {"9040": 35, "9020": 65})
                self.assertEqual(journal.report()["events"][-1][-1], "unknown")
                self.assertEqual(len(journal.report()["events"]), 2)
                self.assertEqual(
                    journal.report()["manual_review_restore_values"], [("9040", 40, 28)]
                )
            with closing(Journal(path)) as restarted:
                with self.assertRaises(ValueError):
                    run(plan, transport, restarted, mode="synthetic")
                self.assertEqual(len(restarted.report()["events"]), 2)

    def test_manual_change_has_priority_over_old_restore_value(self):
        plan = synthetic_plan()
        transport = MemoryTransport(plan)
        with TemporaryDirectory() as folder, closing(Journal(Path(folder) / "test.db")) as journal:
            with self.assertRaises(ValueError):
                run(
                    plan,
                    transport,
                    journal,
                    mode="synthetic",
                    wait=lambda _: transport.words.update({"9040": 45}),
                )
            self.assertEqual(transport.words["9040"], 45)
            self.assertEqual(journal.report()["events"][-1][2], "check-before-restore")
            self.assertEqual(journal.report()["events"][-1][-1], "mismatch")

    def test_every_operation_failure_prevents_all_subsequent_requests(self):
        for failure_index in range(1, 13):
            with self.subTest(failure_index=failure_index), TemporaryDirectory() as folder:
                plan = synthetic_plan()

                class Failure(MemoryTransport):
                    calls = 0

                    def exchange(self, code, function, value):
                        self.calls += 1
                        if self.calls == failure_index:
                            raise OSError("synthetic")
                        return super().exchange(code, function, value)

                transport = Failure(plan)
                with closing(Journal(Path(folder) / "test.db")) as journal:
                    with self.assertRaises(OSError):
                        run(plan, transport, journal, mode="synthetic")
                    self.assertEqual(transport.calls, failure_index)
                    self.assertEqual(journal.report()["run"][2], "stopped-review-required")

    def test_journal_failure_before_request_prevents_dispatch(self):
        with TemporaryDirectory() as folder, closing(Journal(Path(folder) / "test.db")) as journal:
            transport = MemoryTransport(synthetic_plan())
            with (
                patch.object(journal, "reserve", side_effect=OSError),
                patch.object(transport, "exchange") as exchange,
            ):
                with self.assertRaises(OSError):
                    run(synthetic_plan(), transport, journal, mode="synthetic")
                exchange.assert_not_called()

    def test_unconfirmed_encoding_never_opens_socket(self):
        plan = synthetic_plan()
        plan["encoding_confirmed"] = False
        with patch("socket.create_connection") as connect, self.assertRaises(ValueError):
            TcpTransport(plan)
        connect.assert_not_called()

    def test_unknown_registers_fields_duplicate_and_invalid_values_are_rejected(self):
        for key, value in (
            ("code", "9000"),
            ("original_c", True),
            ("test_c", 91),
            ("test_c", 60),
            ("original_c", 60),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan = synthetic_plan()
                plan["registers"][0][key] = value
                validate(plan, live=True)
        plan = synthetic_plan()
        plan["registers"][1] = plan["registers"][0]
        with self.assertRaises(ValueError):
            validate(plan, live=True)

    def test_plan_changes_invalidate_approval_before_any_network(self):
        plan = synthetic_plan()
        approved = fingerprint(plan)
        plan["hold_seconds"] = 1
        with TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_text(json.dumps(plan))
            with redirect_stdout(io.StringIO()), patch("socket.create_connection") as connect:
                self.assertEqual(
                    main(
                        [
                            "execute",
                            "--plan",
                            str(path),
                            "--journal",
                            str(Path(folder) / "test.db"),
                            "--approve",
                            approved,
                        ]
                    ),
                    1,
                )
                connect.assert_not_called()


class FakeSocket:
    """Synthetische Protokollantworten; kein Socket wird geöffnet."""

    def __init__(self, response):
        self.response = response
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def settimeout(self, _):
        pass

    def sendall(self, data):
        self.sent = data

    def recv(self, size):
        # Fragmentierung erzwingen.
        chunk = self.response[:1]
        self.response = self.response[1:]
        return chunk


class WriteProtocolTest(unittest.TestCase):
    def test_cli_complete_cycle_over_real_loopback_tcp(self):
        words = {36928: 40, 36896: 65}
        requests = []

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                data = bytearray()
                while len(data) < 12:
                    part = self.request.recv(12 - len(data))
                    if not part:
                        return
                    data.extend(part)
                transaction, protocol, length, unit, function, offset, value = struct.unpack(
                    ">HHHBBHH", data
                )
                if protocol != 0 or length != 6 or unit != 255 or offset not in words:
                    return
                requests.append((function, offset, value))
                if function == 3 and value == 1:
                    pdu = struct.pack(">BBH", 3, 2, words[offset])
                elif function == 6:
                    decoded = int(str(value), 16)
                    if 10 <= decoded <= 90:
                        words[offset] = decoded
                    pdu = bytes(data[7:])
                else:
                    return
                self.request.sendall(struct.pack(">HHHB", transaction, 0, len(pdu) + 1, 255) + pdu)

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                plan = synthetic_plan()
                plan["port"] = server.server_address[1]
                with TemporaryDirectory() as folder:
                    path = Path(folder) / "plan.json"
                    path.write_text(json.dumps(plan))
                    with redirect_stdout(io.StringIO()):
                        result = main(
                            [
                                "execute",
                                "--plan",
                                str(path),
                                "--journal",
                                str(Path(folder) / "test.db"),
                                "--approve",
                                fingerprint(plan),
                            ]
                        )
                    self.assertEqual(result, 0)
            finally:
                server.shutdown()
                thread.join(timeout=2)
        self.assertEqual(words, {36928: 40, 36896: 65})
        self.assertEqual([function for function, _, _ in requests], [3, 6, 3, 3, 6, 3] * 2)
        self.assertEqual(
            [value for function, _, value in requests if function == 6], [23, 28, 40, 41]
        )

    def exchange(self, pdu, function=6, value=1035, **header):
        response = (
            struct.pack(
                ">HHHB",
                header.get("transaction", 1),
                header.get("protocol", 0),
                header.get("length", len(pdu) + 1),
                header.get("unit", 255),
            )
            + pdu
        )
        connection = FakeSocket(response)
        with patch("socket.create_connection", return_value=connection):
            result = TcpTransport(synthetic_plan()).exchange("9040", function, value)
        return result, connection.sent

    def test_fc06_exact_wire_bytes_and_fc03_fragmentation(self):
        result, sent = self.exchange(b"\x06\x90\x40\x04\x0b")
        self.assertEqual(result, 1035)
        self.assertEqual(sent, bytes.fromhex("000100000006ff069040040b"))
        self.assertEqual(self.exchange(b"\x03\x02\x00\x23", 3, 1)[0], 35)

    def test_bad_echo_headers_exceptions_and_partial_responses_stop(self):
        for pdu, header in (
            (b"\x06\x90\x20\x04\x0b", {}),
            (b"\x86\x02", {}),
            (b"\x06\x90\x40\x04\x0b", {"unit": 1}),
            (b"\x06\x90\x40\x04\x0b", {"protocol": 1}),
            (b"\x06\x90\x40\x04\x0b", {"transaction": 2}),
            (b"\x06\x90", {"length": 6}),
            (b"\x06\x90\x40\x04\x0b", {"length": 255}),
        ):
            with self.subTest(pdu=pdu, header=header), self.assertRaises(ValueError):
                self.exchange(pdu, **header)

    def test_network_failure_has_no_retry(self):
        with patch("socket.create_connection", side_effect=socket.timeout) as connect:
            with self.assertRaises(socket.timeout):
                TcpTransport(synthetic_plan()).exchange("9040", 6, 1035)
            self.assertEqual(connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
