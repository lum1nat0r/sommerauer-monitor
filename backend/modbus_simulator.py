"""Deterministic, loopback-only Modbus TCP simulator for offline transport checks."""

from __future__ import annotations

import argparse
import socket
import socketserver
import threading
import time

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

        if (
            protocol != 0
            or length != 6
            or unit != UNIT_ID
            or function != FUNCTION_READ_HOLDING_REGISTERS
            or (offset, count) not in {(block.offset, block.count) for block in CORE_PROFILE}
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
        request_handler: type[socketserver.BaseRequestHandler] = _Handler,
    ) -> None:
        self.fault = fault
        self.delay_seconds = delay_seconds
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


def _response(transaction: bytes, unit: int, offset: int, count: int) -> bytearray:
    words = {4102: (42,), 28688: (4, 319), 36864: (47, 38)}[offset][:count]
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
