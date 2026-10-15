from __future__ import annotations

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

import backend.modbus as transport
from backend.catalog import CatalogReadBlock, CatalogUnavailable, load_catalog
from backend.modbus import (
    ConnectionError,
    IncompleteResponseError,
    ModbusTcpClient,
    ProtocolError,
    RegisterRead,
)
from backend.modbus_simulator import ModbusSimulator
from backend.registers import CORE_PROFILE, RegisterBlock, decode_register_block


def _client(simulator: ModbusSimulator, deadline: float = 1.0) -> ModbusTcpClient:
    host, port = simulator.address
    return ModbusTcpClient(host, port, deadline_seconds=deadline)


def _read(client: ModbusTcpClient, path: str) -> RegisterRead:
    if path == "core":
        return client.read(CORE_PROFILE[1])
    return client.read_catalog(CatalogReadBlock(33408, 1))


def _request(path: str) -> tuple[int, int, int, int]:
    return (255, 3, 28688, 2) if path == "core" else (255, 3, 33408, 1)


@pytest.mark.parametrize("path", ["core", "catalog"])
@pytest.mark.parametrize("fault", ["valid", "fragmented"])
def test_reads_exact_raw_words_without_followup_requests(path: str, fault: str) -> None:
    with ModbusSimulator(fault, catalog=True) as simulator:
        result = _read(_client(simulator), path)
        assert simulator.received_requests == (_request(path),)

    assert (result.offset, result.words, result.unit_id, result.function_code) == (
        (28688, (4, 319), 255, 3) if path == "core" else (33408, (65526,), 255, 3)
    )
    with pytest.raises(FrozenInstanceError):
        result.offset = 0
    with pytest.raises(TypeError):
        result.words[0] = 0


@pytest.mark.parametrize("path", ["core", "catalog"])
@pytest.mark.parametrize(
    ("fault", "error_type", "core_bytes", "catalog_bytes"),
    [
        ("wrong_unit", ProtocolError, 7, 7),
        ("wrong_transaction", ProtocolError, 7, 7),
        ("wrong_protocol", ProtocolError, 7, 7),
        ("wrong_length", ProtocolError, 12, 10),
        ("wrong_function", ProtocolError, 13, 11),
        ("wrong_byte_count", ProtocolError, 13, 11),
        ("exception", ProtocolError, 9, 9),
        ("incomplete", IncompleteResponseError, 11, 9),
        ("close_no_data", ConnectionError, 0, 0),
        ("close_partial", IncompleteResponseError, 1, 1),
        ("delayed", ConnectionError, 0, 0),
    ],
)
def test_faults_report_exact_bytes_without_retry(
    path: str,
    fault: str,
    error_type: type[Exception],
    core_bytes: int,
    catalog_bytes: int,
) -> None:
    with ModbusSimulator(fault, catalog=True, delay_seconds=0.15) as simulator:
        with pytest.raises(error_type) as error:
            _read(_client(simulator, deadline=0.05 if fault == "delayed" else 1.0), path)
        assert simulator.received_requests == (_request(path),)

    assert type(error.value) is error_type
    assert error.value.received_bytes == (core_bytes if path == "core" else catalog_bytes)


def test_catalog_special_values_are_three_explicit_fc03_requests() -> None:
    with ModbusSimulator(catalog=True) as simulator:
        client = _client(simulator)
        results = tuple(
            client.read_catalog(CatalogReadBlock(offset, 1)) for offset in (4098, 4099, 33408)
        )
        assert simulator.received_requests == (
            (255, 3, 4098, 1),
            (255, 3, 4099, 1),
            (255, 3, 33408, 1),
        )

    assert tuple(result.words for result in results) == ((0,), (173,), (65526,))


def test_catalog_returns_every_documented_word_without_interpretation() -> None:
    core_words = {4102: 42, 28688: 4, 28689: 319, 36864: 47, 36865: 38}
    special_words = {4098: 0, 4099: 173, 33408: 65526}
    offsets = tuple(sorted(load_catalog().entries))
    with ModbusSimulator(catalog=True) as simulator:
        client = _client(simulator)
        for offset in offsets:
            result = client.read_catalog(CatalogReadBlock(offset, 1))
            expected = core_words.get(offset, special_words.get(offset, (offset * 17 + 3) & 0xFFFF))
            assert (result.offset, result.words, result.unit_id, result.function_code) == (
                offset, (expected,), 255, 3
            )
        assert simulator.received_requests == tuple((255, 3, offset, 1) for offset in offsets)


@pytest.mark.parametrize("catalog", [False, True])
@pytest.mark.parametrize("path", ["core", "catalog"])
def test_exact_core_blocks_keep_values_and_existing_counter_decoder(
    catalog: bool, path: str
) -> None:
    with ModbusSimulator(catalog=catalog) as simulator:
        client = _client(simulator)
        results = tuple(
            client.read(block) if path == "core"
            else client.read_catalog(CatalogReadBlock(block.offset, block.count))
            for block in CORE_PROFILE
        )
        assert simulator.received_requests == (
            (255, 3, 4102, 1), (255, 3, 28688, 2), (255, 3, 36864, 2)
        )

    assert tuple(result.words for result in results) == ((42,), (4, 319), (47, 38))
    decoded = decode_register_block(results[1].offset, results[1].words)
    assert (decoded[0].value, decoded[0].unit, decoded[0].raw_words) == (6079, "min", (4, 319))


@pytest.mark.parametrize(
    "block",
    [
        CatalogReadBlock(True, 1),
        CatalogReadBlock(False, 1),
        CatalogReadBlock(4102, True),
        CatalogReadBlock(4102, False),
        CatalogReadBlock(4102.0, 1),
        CatalogReadBlock(4102, 1.0),
        CatalogReadBlock("4102", 1),
        CatalogReadBlock(4102, "1"),
        CatalogReadBlock(None, 1),
        CatalogReadBlock(4102, None),
        CatalogReadBlock(-1, 1),
        CatalogReadBlock(65536, 1),
        CatalogReadBlock(65535, 2),
        CatalogReadBlock(4102, -1),
        CatalogReadBlock(4102, 0),
        CatalogReadBlock(4102, 3),
        CatalogReadBlock(4102, 65536),
        CatalogReadBlock(0, 1),
        CatalogReadBlock(4103, 1),
        CatalogReadBlock(36928, 1),
        CatalogReadBlock(36896, 1),
        CatalogReadBlock(4098, 2),
        CatalogReadBlock(4099, 2),
        CatalogReadBlock(4102, 2),
        CatalogReadBlock(28689, 2),
        CatalogReadBlock(36865, 2),
        CORE_PROFILE[0],
        (4102, 1),
        {"offset": 4102, "count": 1},
        SimpleNamespace(offset=4102, count=1),
        None,
    ],
)
def test_catalog_rejects_noncanonical_blocks_before_any_socket(
    monkeypatch: pytest.MonkeyPatch, block: object
) -> None:
    def forbidden_socket(*args: object, **kwargs: object) -> None:
        pytest.fail("Ungültiger Katalogblock darf keinen Socket öffnen")

    with ModbusSimulator(catalog=True) as simulator:
        client = _client(simulator)
        with monkeypatch.context() as patch:
            patch.setattr(transport.socket, "create_connection", forbidden_socket)
            with pytest.raises(ValueError):
                client.read_catalog(block)
        assert simulator.received_requests == ()


@pytest.mark.parametrize(
    "block",
    [
        RegisterBlock(4103, 1, ("other",)),
        RegisterBlock(4102, 3, ()),
        RegisterBlock(4102, 1, ("other",)),
        RegisterBlock(4102, True, CORE_PROFILE[0].signal_ids),
        RegisterBlock(4102.0, 1, CORE_PROFILE[0].signal_ids),
        RegisterBlock(28688, 1, CORE_PROFILE[1].signal_ids),
        RegisterBlock(28689, 1, CORE_PROFILE[1].signal_ids),
        RegisterBlock(36864, 1, CORE_PROFILE[2].signal_ids),
        RegisterBlock(4098, 1, ()),
        CatalogReadBlock(4102, 1),
        SimpleNamespace(offset=4102, count=1, signal_ids=CORE_PROFILE[0].signal_ids),
        None,
    ],
)
def test_core_boundary_remains_exact_before_any_socket(
    monkeypatch: pytest.MonkeyPatch, block: object
) -> None:
    def forbidden_socket(*args: object, **kwargs: object) -> None:
        pytest.fail("Nicht exakter Kernblock darf keinen Socket öffnen")

    with ModbusSimulator(catalog=True) as simulator:
        client = _client(simulator)
        with monkeypatch.context() as patch:
            patch.setattr(transport.socket, "create_connection", forbidden_socket)
            with pytest.raises(ValueError):
                client.read(block)
        assert simulator.received_requests == ()


def test_broken_catalog_blocks_diagnostics_but_not_core_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_catalog() -> None:
        raise CatalogUnavailable()

    def forbidden_socket(*args: object, **kwargs: object) -> None:
        pytest.fail("Defekter Katalog darf keinen Diagnosesocket öffnen")

    with ModbusSimulator() as simulator:
        client = _client(simulator)
        monkeypatch.setattr(transport, "load_catalog", unavailable_catalog)
        with monkeypatch.context() as patch:
            patch.setattr(transport.socket, "create_connection", forbidden_socket)
            with pytest.raises(CatalogUnavailable) as error:
                client.read_catalog(CatalogReadBlock(4098, 1))
        assert error.value.code == "catalog_unavailable"
        assert simulator.received_requests == ()
        assert client.read(CORE_PROFILE[0]).words == (42,)
        assert simulator.received_requests == ((255, 3, 4102, 1),)


def test_received_requests_is_a_read_only_immutable_snapshot() -> None:
    with ModbusSimulator(catalog=True) as simulator:
        client = _client(simulator)
        empty = simulator.received_requests
        client.read_catalog(CatalogReadBlock(4098, 1))
        first = simulator.received_requests
        assert first == ((255, 3, 4098, 1),)
        with pytest.raises(TypeError):
            first[0] = (255, 3, 4099, 1)
        with pytest.raises(TypeError):
            first[0][2] = 4099
        with pytest.raises(AttributeError):
            simulator.received_requests = ()
        client.read_catalog(CatalogReadBlock(4099, 1))
        second = simulator.received_requests

    assert empty == ()
    assert first == ((255, 3, 4098, 1),)
    assert second == ((255, 3, 4098, 1), (255, 3, 4099, 1))


@pytest.mark.parametrize(
    ("catalog", "offset", "count"),
    [(False, 4098, 1), (False, 28689, 1), (True, 4103, 1), (True, 4098, 2)],
)
def test_simulator_enforces_its_own_mode_boundary(
    catalog: bool, offset: int, count: int
) -> None:
    # Direkter FC03-Loopback-Request prüft die Simulatorgrenze unabhängig vom Client.
    request = b"\x12\x34\x00\x00\x00\x06\xff\x03"
    request += offset.to_bytes(2, "big") + count.to_bytes(2, "big")
    with ModbusSimulator(catalog=catalog) as simulator:
        with socket.create_connection(simulator.address, timeout=1) as connection:
            connection.sendall(request)
            response = bytearray()
            while len(response) < 9:
                chunk = connection.recv(9 - len(response))
                assert chunk
                response.extend(chunk)
        assert simulator.received_requests == ((255, 3, offset, count),)

    assert response == b"\x12\x34\x00\x00\x00\x03\xff\x83\x02"


class _ObservedLock:
    """Gatet den zweiten Eintritt, ohne das echte Lockverhalten zu ersetzen."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._guard = threading.Lock()
        self._calls = 0
        self.second_waiting = threading.Event()

    def acquire(self, *, timeout: float) -> bool:
        with self._guard:
            self._calls += 1
            if self._calls == 2:
                self.second_waiting.set()
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        self._lock.release()


class _GatedSocket:
    """In-process-Socket mit echter Thread-Gate und vollständigen FC03-Antworten."""

    def __init__(self, state: SimpleNamespace, *, first: bool) -> None:
        self.state = state
        self.first = first
        self.response = b""
        self.timeout = 1.0

    def __enter__(self) -> _GatedSocket:
        return self

    def __exit__(self, *_: object) -> None:
        self.state.active -= 1

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendall(self, request: bytes) -> None:
        self.state.requests.append(request)
        offset = int.from_bytes(request[8:10], "big")
        words = (4, 319) if offset == 28688 else (65526,)
        pdu = bytes((3, len(words) * 2)) + b"".join(word.to_bytes(2, "big") for word in words)
        self.response = request[:2] + b"\x00\x00" + bytes((0, len(pdu) + 1, 255)) + pdu

    def recv(self, size: int) -> bytes:
        if self.first:
            self.state.entered.set()
            started = time.perf_counter()
            released = self.state.release.wait(timeout=3)
            if not released or time.perf_counter() - started >= self.timeout:
                raise socket.timeout()
        chunk, self.response = self.response[:size], self.response[size:]
        return chunk


def _gated_client(
    monkeypatch: pytest.MonkeyPatch, deadline: float
) -> tuple[ModbusTcpClient, SimpleNamespace, _ObservedLock]:
    state = SimpleNamespace(
        active=0, maximum=0, calls=0, requests=[],
        entered=threading.Event(), release=threading.Event(),
    )

    def connect(address: tuple[str, int], *, timeout: float) -> _GatedSocket:
        assert address == ("127.0.0.1", 1502)
        state.calls += 1
        state.active += 1
        state.maximum = max(state.maximum, state.active)
        return _GatedSocket(state, first=state.calls == 1)

    monkeypatch.setattr(transport.socket, "create_connection", connect)
    client = ModbusTcpClient("127.0.0.1", 1502, deadline_seconds=deadline)
    lock = _ObservedLock()
    monkeypatch.setattr(client, "_request_lock", lock)
    return client, state, lock


@pytest.mark.parametrize("first_path", ["core", "catalog"])
def test_concurrent_core_and_catalog_reads_never_open_parallel_sockets(
    monkeypatch: pytest.MonkeyPatch, first_path: str
) -> None:
    client, state, lock = _gated_client(monkeypatch, deadline=3.0)
    second_path = "catalog" if first_path == "core" else "core"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_read, client, first_path)
        try:
            assert state.entered.wait(timeout=1)
            second = pool.submit(_read, client, second_path)
            assert lock.second_waiting.wait(timeout=1)
            assert state.calls == state.active == state.maximum == 1
        finally:
            state.release.set()
        first_result = first.result(timeout=3)
        second_result = second.result(timeout=3)

    assert first_result.words == ((4, 319) if first_path == "core" else (65526,))
    assert second_result.words == ((4, 319) if second_path == "core" else (65526,))
    assert state.calls == 2
    assert state.maximum == 1
    assert state.active == 0
    assert tuple(
        (request[6], request[7], int.from_bytes(request[8:10], "big"),
         int.from_bytes(request[10:12], "big"))
        for request in state.requests
    ) == (_request(first_path), _request(second_path))


@pytest.mark.parametrize("first_path", ["core", "catalog"])
def test_lock_wait_consumes_the_same_deadline_without_opening_a_second_socket(
    monkeypatch: pytest.MonkeyPatch, first_path: str
) -> None:
    client, state, lock = _gated_client(monkeypatch, deadline=0.2)
    second_path = "catalog" if first_path == "core" else "core"

    def timed_second() -> tuple[ConnectionError, float]:
        started = time.perf_counter()
        with pytest.raises(ConnectionError) as error:
            _read(client, second_path)
        return error.value, time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_read, client, first_path)
        try:
            assert state.entered.wait(timeout=1)
            second = pool.submit(timed_second)
            assert lock.second_waiting.wait(timeout=1)
            # Das Testgate hält den ersten Socket unabhängig von dessen Deadline.
            # Nach Freigabe meldet es dessen bereits verstrichenen Timeout.
            error, elapsed = second.result(timeout=1)
        finally:
            state.release.set()
        with pytest.raises(ConnectionError) as first_error:
            first.result(timeout=1)

    assert error.received_bytes == first_error.value.received_bytes == 0
    # 0,3 s Scheduler-Toleranz zum 0,2-s-Budget, deutlich unter der 3-s-Obergrenze.
    assert 0.15 <= elapsed <= 0.5
    assert state.calls == state.maximum == 1
    assert state.active == 0
    assert len(state.requests) == 1


@pytest.mark.parametrize("path", ["core", "catalog"])
@pytest.mark.parametrize("lock_wait", [0.0, 0.08])
def test_slow_fragments_do_not_restart_lock_connect_send_receive_deadline(
    monkeypatch: pytest.MonkeyPatch, path: str, lock_wait: float
) -> None:
    clock = SimpleNamespace(now=0.0)
    timeouts: list[float] = []
    requests: list[bytes] = []
    connections: list[tuple[str, int]] = []

    class TimedLock:
        def acquire(self, *, timeout: float) -> bool:
            assert timeout == pytest.approx(0.35)
            clock.now += lock_wait
            return True

        def release(self) -> None:
            pass

    class SlowSocket:
        def __init__(self) -> None:
            self.response = b""
            self.timeout = 0.0

        def __enter__(self) -> SlowSocket:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def settimeout(self, timeout: float) -> None:
            self.timeout = timeout
            timeouts.append(timeout)

        def sendall(self, request: bytes) -> None:
            requests.append(request)
            clock.now += 0.05
            words = b"\x00\x04\x01\x3f" if path == "core" else b"\xff\xf6"
            pdu = bytes((3, len(words))) + words
            self.response = request[:2] + b"\x00\x00" + bytes((0, len(pdu) + 1, 255)) + pdu

        def recv(self, size: int) -> bytes:
            if self.timeout < 0.1 - 1e-9:
                clock.now += self.timeout
                raise socket.timeout()
            clock.now += 0.1
            chunk, self.response = self.response[:1], self.response[1:]
            return chunk

    def connect(address: tuple[str, int], *, timeout: float) -> SlowSocket:
        connections.append(address)
        timeouts.append(timeout)
        clock.now += 0.05
        return SlowSocket()

    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(transport.socket, "create_connection", connect)
    client = ModbusTcpClient("127.0.0.1", 1502, deadline_seconds=0.35)
    monkeypatch.setattr(client, "_request_lock", TimedLock())
    with pytest.raises(IncompleteResponseError) as error:
        _read(client, path)

    assert error.value.received_bytes == (2 if lock_wait == 0 else 1)
    assert clock.now == pytest.approx(0.35)
    assert timeouts == pytest.approx(
        [0.35, 0.3, 0.25, 0.15, 0.05]
        if lock_wait == 0 else [0.27, 0.22, 0.17, 0.07]
    )
    assert connections == [("127.0.0.1", 1502)]
    assert len(requests) == 1


def test_simulator_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        ModbusSimulator(host="192.0.2.1")


def test_simulator_is_reachable_only_on_local_socket() -> None:
    with ModbusSimulator() as simulator:
        host, port = simulator.address
        assert host == "127.0.0.1"
        with socket.create_connection((host, port), timeout=1):
            pass
        assert simulator.received_requests == ()
