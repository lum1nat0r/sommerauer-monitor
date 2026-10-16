from __future__ import annotations

import socket

import pytest

from backend.modbus import (
    ConnectionError,
    IncompleteResponseError,
    ModbusTcpClient,
    ProtocolError,
)
from backend.modbus_simulator import ModbusSimulator
from backend.registers import CORE_PROFILE, RegisterBlock


def _client(simulator: ModbusSimulator, deadline: float = 1.0) -> ModbusTcpClient:
    host, port = simulator.address
    return ModbusTcpClient(host, port, deadline_seconds=deadline)


def test_reads_confirmed_block_through_fragmented_tcp_response() -> None:
    with ModbusSimulator("fragmented") as simulator:
        result = _client(simulator).read(CORE_PROFILE[1])

    assert (result.offset, result.words, result.unit_id, result.function_code) == (
        28688,
        (4, 319),
        255,
        3,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_unit",
        "wrong_transaction",
        "wrong_protocol",
        "wrong_length",
        "wrong_function",
        "wrong_byte_count",
        "exception",
    ],
)
def test_rejects_invalid_responses(fault: str) -> None:
    with ModbusSimulator(fault) as simulator, pytest.raises(ProtocolError):
        _client(simulator).read(CORE_PROFILE[0])


def test_no_response_bytes_and_partial_response_are_distinct() -> None:
    with ModbusSimulator("close_no_data") as simulator, pytest.raises(ConnectionError) as no_bytes:
        _client(simulator).read(CORE_PROFILE[0])
    with ModbusSimulator("close_partial") as simulator, pytest.raises(
        IncompleteResponseError
    ) as partial:
        _client(simulator).read(CORE_PROFILE[0])

    assert no_bytes.value.received_bytes == 0
    assert partial.value.received_bytes == 1


def test_timeout_without_response_bytes_is_connection_error() -> None:
    with ModbusSimulator("delayed", delay_seconds=0.1) as simulator:
        with pytest.raises(ConnectionError) as timeout:
            _client(simulator, deadline=0.02).read(CORE_PROFILE[0])

    assert timeout.value.received_bytes == 0


def test_incomplete_response_reports_received_byte_count() -> None:
    with ModbusSimulator("incomplete") as simulator, pytest.raises(
        IncompleteResponseError
    ) as error:
        _client(simulator).read(CORE_PROFILE[1])

    assert error.value.received_bytes > 0


def test_transport_accepts_only_exact_profile_blocks_and_has_no_write_api() -> None:
    with ModbusSimulator() as simulator:
        client = _client(simulator)
        for unauthorized in (RegisterBlock(4103, 1, ("other",)), RegisterBlock(4102, 3, ())):
            with pytest.raises(ValueError):
                client.read(unauthorized)
        assert not hasattr(client, "write")


def test_simulator_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        ModbusSimulator(host="192.0.2.1")


def test_simulator_is_reachable_only_on_local_socket() -> None:
    with ModbusSimulator() as simulator:
        host, port = simulator.address
        assert host in {"127.0.0.1", "::1"}
        with socket.create_connection((host, port), timeout=1):
            pass
