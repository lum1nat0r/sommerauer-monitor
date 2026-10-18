"""Enger FC03-Lesetransport für die explizit quellengeprüften Registerblöcke."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass

from backend.registers import READ_PROFILE, RegisterBlock

UNIT_ID = 255
FUNCTION_READ_HOLDING_REGISTERS = 3
MAX_REGISTERS = 2
DEFAULT_DEADLINE_SECONDS = 3.0


class ModbusError(Exception):
    """Base transport error with the number of response bytes observed."""

    def __init__(self, message: str, *, received_bytes: int = 0) -> None:
        super().__init__(message)
        self.received_bytes = received_bytes


class ConnectionError(ModbusError):
    """Connection failure or timeout before any response byte arrived."""


class IncompleteResponseError(ModbusError):
    """The peer disconnected or the deadline expired after a partial response."""


class ProtocolError(ModbusError):
    """A complete or incomplete response violated the Modbus contract."""


class ModbusExceptionError(ProtocolError):
    """A structurally valid exception PDU rejects this register block."""

    def __init__(self, exception_code: int, *, received_bytes: int = 0) -> None:
        super().__init__(
            f"Modbus exception code {exception_code}", received_bytes=received_bytes
        )
        self.exception_code = exception_code


@dataclass(frozen=True, slots=True)
class RegisterRead:
    offset: int
    words: tuple[int, ...]
    unit_id: int = UNIT_ID
    function_code: int = FUNCTION_READ_HOLDING_REGISTERS


class ModbusTcpClient:
    """Genau einen explizit zugelassenen Block lesen, ohne eigene Wiederholungen."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        *,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ) -> None:
        if not host.strip():
            raise ValueError("host must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("port must be in 1..65535")
        if not 0 < deadline_seconds <= DEFAULT_DEADLINE_SECONDS:
            raise ValueError("deadline_seconds must be in 0..3 seconds")
        self._host = host
        self._port = port
        self._deadline_seconds = deadline_seconds
        self._request_lock = threading.Lock()
        self._transaction_id = 0

    def read(self, block: RegisterBlock) -> RegisterRead:
        """Nur vollständig übereinstimmende Profilblöcke lesen; feste Unit 255."""
        if block not in READ_PROFILE:
            raise ValueError("only blocks from the explicit read profile are allowed")
        if not 1 <= block.count <= MAX_REGISTERS:
            raise ValueError("FC03 reads are limited to two registers")

        deadline = time.monotonic() + self._deadline_seconds
        if not self._request_lock.acquire(timeout=self._remaining(deadline)):
            raise ConnectionError("request deadline elapsed waiting for the client")
        try:
            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            transaction_id = self._transaction_id
            request = (
                transaction_id.to_bytes(2, "big")
                + b"\x00\x00\x00\x06"
                + bytes((UNIT_ID, FUNCTION_READ_HOLDING_REGISTERS))
                + block.offset.to_bytes(2, "big")
                + block.count.to_bytes(2, "big")
            )
            received = bytearray()
            try:
                with socket.create_connection(
                    (self._host, self._port), timeout=self._remaining(deadline)
                ) as connection:
                    connection.settimeout(self._remaining(deadline))
                    connection.sendall(request)
                    header = self._recv_exact(connection, 7, received, deadline)
                    response_transaction = int.from_bytes(header[0:2], "big")
                    protocol_id = int.from_bytes(header[2:4], "big")
                    length = int.from_bytes(header[4:6], "big")
                    unit_id = header[6]
                    if response_transaction != transaction_id:
                        raise ProtocolError(
                            "transaction identifier mismatch", received_bytes=len(received)
                        )
                    if protocol_id != 0:
                        raise ProtocolError(
                            "protocol identifier must be zero", received_bytes=len(received)
                        )
                    if not 2 <= length <= 254:
                        raise ProtocolError("invalid MBAP length", received_bytes=len(received))
                    if unit_id != UNIT_ID:
                        raise ProtocolError("unit identifier mismatch", received_bytes=len(received))
                    pdu = self._recv_exact(connection, length - 1, received, deadline)
            except socket.timeout as exc:
                self._raise_incomplete_or_connection(
                    "Modbus response deadline elapsed", received, exc
                )
            except OSError as exc:
                self._raise_incomplete_or_connection("Modbus TCP connection failed", received, exc)
            function = pdu[0]
            if function == (FUNCTION_READ_HOLDING_REGISTERS | 0x80):
                if len(pdu) != 2:
                    raise ProtocolError(
                        "malformed Modbus exception response", received_bytes=len(received)
                    )
                raise ModbusExceptionError(pdu[1], received_bytes=len(received))
            if function != FUNCTION_READ_HOLDING_REGISTERS:
                raise ProtocolError("function code mismatch", received_bytes=len(received))
            expected_byte_count = block.count * 2
            if len(pdu) != 2 + expected_byte_count or pdu[1] != expected_byte_count:
                raise ProtocolError("register byte count mismatch", received_bytes=len(received))
            words = tuple(
                int.from_bytes(pdu[index : index + 2], "big")
                for index in range(2, len(pdu), 2)
            )
            return RegisterRead(block.offset, words)
        finally:
            self._request_lock.release()

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConnectionError("Modbus request deadline elapsed")
        return remaining

    @classmethod
    def _recv_exact(
        cls, connection: socket.socket, size: int, received: bytearray, deadline: float
    ) -> bytes:
        result = bytearray()
        while len(result) < size:
            try:
                connection.settimeout(cls._remaining(deadline))
            except ConnectionError as exc:
                cls._raise_incomplete_or_connection(
                    "Modbus response deadline elapsed", received, exc
                )
            chunk = connection.recv(size - len(result))
            if not chunk:
                cls._raise_incomplete_or_connection(
                    "peer closed before the Modbus response was complete", received
                )
            result.extend(chunk)
            received.extend(chunk)
        return bytes(result)

    @staticmethod
    def _raise_incomplete_or_connection(
        message: str, received: bytearray, cause: OSError | None = None
    ) -> None:
        error_type = IncompleteResponseError if received else ConnectionError
        error = error_type(message, received_bytes=len(received))
        if cause is not None:
            raise error from cause
        raise error
