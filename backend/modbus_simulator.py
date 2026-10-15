"""Deterministischer Loopback-Simulator; alle Rohworte sind synthetische Testdaten."""

from __future__ import annotations

import argparse
import socket
import socketserver
import threading
import time

from backend.catalog import RegisterCatalog, load_catalog
from backend.modbus import FUNCTION_READ_HOLDING_REGISTERS, UNIT_ID
from backend.registers import CORE_PROFILE

FAULTS = (
    "valid",
    "fragmented",
    "delayed",
    "incomplete",
    "wrong_unit",
    "wrong_transaction",
    "wrong_protocol",
    "wrong_length",
    "wrong_function",
    "wrong_byte_count",
    "exception",
    "close_no_data",
    "close_partial",
)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        connection: socket.socket = self.request
        request = _recv_exact(connection, 12)
        if len(request) != 12:
            return
        transaction = request[0:2]
        protocol = int.from_bytes(request[2:4], "big")
        length = int.from_bytes(request[4:6], "big")
        unit = request[6]
        function = request[7]
        offset = int.from_bytes(request[8:10], "big")
        count = int.from_bytes(request[10:12], "big")
        self.server.record_request((unit, function, offset, count))  # type: ignore[attr-defined]

        if (
            protocol != 0
            or length != 6
            or unit != UNIT_ID
            or function != FUNCTION_READ_HOLDING_REGISTERS
            or not self.server.allows_block(offset, count)  # type: ignore[attr-defined]
        ):
            connection.sendall(_exception(transaction, unit, function, 2))
            return

        mode = self.server.fault  # type: ignore[attr-defined]
        if mode == "close_no_data":
            return
        if mode == "close_partial":
            connection.sendall(transaction[:1])
            return
        if mode == "delayed":
            time.sleep(self.server.delay_seconds)  # type: ignore[attr-defined]
        response = _response(transaction, unit, offset, count)
        if mode == "wrong_unit":
            response[6] = (UNIT_ID - 1) & 0xFF
        elif mode == "wrong_transaction":
            response[0] ^= 1
        elif mode == "wrong_protocol":
            response[2] = 1
        elif mode == "wrong_length":
            response[5] -= 1
        elif mode == "wrong_function":
            response[7] = 4
        elif mode == "wrong_byte_count":
            response[8] += 2
        elif mode == "exception":
            response = bytearray(_exception(transaction, unit, function, 2))
        elif mode == "incomplete":
            connection.sendall(response[:-2])
            return
        if mode == "fragmented":
            for byte in response:
                connection.sendall(bytes((byte,)))
                time.sleep(0.001)
        else:
            connection.sendall(response)


class _Server(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        fault: str,
        delay_seconds: float,
        catalog: RegisterCatalog | None,
        request_handler: type[socketserver.BaseRequestHandler] = _Handler,
    ) -> None:
        self.fault = fault
        self.delay_seconds = delay_seconds
        self._catalog = catalog
        self._received_requests: list[tuple[int, int, int, int]] = []
        self._requests_lock = threading.Lock()
        super().__init__(address, request_handler)

    def allows_block(self, offset: int, count: int) -> bool:
        return any(block.offset == offset and block.count == count for block in CORE_PROFILE) or (
            self._catalog is not None and count == 1 and offset in self._catalog.entries
        )

    def record_request(self, request: tuple[int, int, int, int]) -> None:
        with self._requests_lock:
            self._received_requests.append(request)

    @property
    def received_requests(self) -> tuple[tuple[int, int, int, int], ...]:
        with self._requests_lock:
            return tuple(self._received_requests)


class ModbusSimulator:
    """Offline-Simulator: standardmäßig nur Kernblöcke, optional Katalogrohworte."""

    def __init__(
        self,
        fault: str = "valid",
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        delay_seconds: float = 3.5,
        catalog: bool = False,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("simulator may bind only to the 127.0.0.1 loopback address")
        if fault not in FAULTS:
            raise ValueError(f"unknown simulator fault: {fault}")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if type(catalog) is not bool:
            raise ValueError("catalog must be a boolean")
        catalog_snapshot = load_catalog() if catalog else None
        self._server = _Server((host, port), fault, delay_seconds, catalog_snapshot)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def received_requests(self) -> tuple[tuple[int, int, int, int], ...]:
        """Unveränderliche Momentaufnahme empfangener Anfragen, kein Anlagenlog."""
        return self._server.received_requests

    def __enter__(self) -> ModbusSimulator:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


def _response(transaction: bytes, unit: int, offset: int, count: int) -> bytearray:
    # Keine Einheiten-/Anlagenbelege: feste Kernworte und explizite Testsonderfälle.
    fixed_words = {
        4102: 42,
        28688: 4,
        28689: 319,
        36864: 47,
        36865: 38,
        4098: 0,
        4099: 173,
        33408: 65526,
    }
    words = (
        fixed_words.get(word_offset, (word_offset * 17 + 3) & 0xFFFF)
        for word_offset in range(offset, offset + count)
    )
    pdu = bytes((FUNCTION_READ_HOLDING_REGISTERS, count * 2)) + b"".join(
        word.to_bytes(2, "big") for word in words
    )
    return bytearray(transaction + b"\x00\x00" + (len(pdu) + 1).to_bytes(2, "big") + bytes((unit,)) + pdu)


def _exception(transaction: bytes, unit: int, function: int, code: int) -> bytes:
    pdu = bytes((function | 0x80, code))
    return transaction + b"\x00\x00" + (len(pdu) + 1).to_bytes(2, "big") + bytes((unit,)) + pdu


def _recv_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
    return bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--fault", choices=FAULTS, default="valid")
    parser.add_argument(
        "--catalog", action="store_true", help="Dokumentierte Einzelregister synthetisch beantworten"
    )
    args = parser.parse_args()
    with ModbusSimulator(args.fault, port=args.port, catalog=args.catalog) as simulator:
        print(f"Offline Modbus simulator listening on {simulator.address[0]}:{simulator.address[1]}")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
