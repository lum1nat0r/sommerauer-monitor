"""Deterministic, loopback-only Modbus TCP simulator for offline transport checks."""

from __future__ import annotations

import argparse
import socket
import socketserver
import threading
import time

from backend.modbus import FUNCTION_READ_HOLDING_REGISTERS, UNIT_ID
from backend.registers import READ_PROFILE, REGISTER_DEFINITIONS

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

# Deliberately synthetic fixtures, not device readings or inferred installation values.
_SYNTHETIC_WORDS = {
    definition["offset"]: 20 for definition in REGISTER_DEFINITIONS.values()
}
_SYNTHETIC_WORDS.update({
    0x1001: 2,
    0x1000: 7, 0x1007: 65, 0x9020: 60, 0x9040: 40,
    0x1005: 100, 0x1012: 0,
    0x1002: 0, 0x1003: 50, 0x1006: 42, 0x1008: 50, 0x100A: 240,
    0x1021: 0, 0x1023: 0, 0x10D1: 1,
    0x1100: 120, 0x1101: 120, 0x1102: 120, 0x1104: 500, 0x1105: 500,
    0x12F0: 20, 0x1320: 500, 0x1321: 500, 0x1323: 500,
    0x7002: 0, 0x7003: 15, 0x7004: 6, 0x7005: 2026, 0x7006: 720,
    0x7010: 4, 0x7011: 319, 0x7012: 1, 0x7013: 120,
    0x8000: 1, 0x8001: 1, 0x85E0: 20, 0x85E1: 20, 0x8BF0: 20, 0x8BF1: 20,
    0x8E0F: 20, 0x8E1F: 20, 0x8E40: 50, 0x8E41: 50,
    0x9000: 47, 0x9001: 38, 0x9140: 0, 0x9141: 0, 0x91E0: 50, 0x91E1: 50,
    0x95E0: 20, 0x95E1: 20,
})
_ALLOWED_BLOCKS = {(block.offset, block.count) for block in READ_PROFILE}


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

        if (
            protocol != 0
            or length != 6
            or unit != UNIT_ID
            or function != FUNCTION_READ_HOLDING_REGISTERS
            or (offset, count) not in _ALLOWED_BLOCKS
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
        values = self.server.words  # type: ignore[attr-defined]
        words = tuple(values[address] for address in range(offset, offset + count))
        response = _response(transaction, unit, words)
        for address in range(offset, offset + count):
            if REGISTER_DEFINITIONS[f"{address:04X}"]["read_to_clear"]:
                values[address] = 0
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
        request_handler: type[socketserver.BaseRequestHandler] = _Handler,
    ) -> None:
        self.fault = fault
        self.delay_seconds = delay_seconds
        self.words = dict(_SYNTHETIC_WORDS)
        super().__init__(address, request_handler)


class ModbusSimulator:
    """Context-managed simulator; its default and CLI bind are loopback only."""

    def __init__(
        self,
        fault: str = "valid",
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        delay_seconds: float = 3.5,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("simulator may bind only to the 127.0.0.1 loopback address")
        if fault not in FAULTS:
            raise ValueError(f"unknown simulator fault: {fault}")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        self._server = _Server((host, port), fault, delay_seconds)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def __enter__(self) -> ModbusSimulator:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


def _response(transaction: bytes, unit: int, words: tuple[int, ...]) -> bytearray:
    count = len(words)
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
    args = parser.parse_args()
    with ModbusSimulator(args.fault, port=args.port) as simulator:
        print(f"Offline Modbus simulator listening on {simulator.address[0]}:{simulator.address[1]}")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
