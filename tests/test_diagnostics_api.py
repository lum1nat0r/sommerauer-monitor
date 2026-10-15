"""Synthetische HTTP-Abnahme; nur tmp_path, explizite Settings und Loopback."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from backend import main
from backend.catalog import CatalogUnavailable, load_catalog
from backend.config import Settings
from backend.device_lock import DeviceLock
from backend.modbus import (
    ConnectionError as ModbusConnectionError,
    IncompleteResponseError,
    ModbusTcpClient,
    ProtocolError,
    RegisterRead,
)
from backend.modbus_simulator import ModbusSimulator
from backend.storage import SQLiteStore, StorageError


BASE = "/api/diagnostics"
HEADERS = {
    "Origin": "http://testserver",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "SommerauerMonitor",
}
PRIVATE_ERROR = "synthetisch-privat.invalid C:/synthetisch/geheim.sqlite3"
PLAN_FIELDS = {
    "schema_version", "catalog_sha256", "register_ids", "blocks", "purpose", "source",
    "target_alias", "function_code", "unit_id", "deadline_seconds", "request_budget",
    "min_interval_seconds", "max_duration_seconds", "stop_conditions",
}
REQUEST_FIELDS = {
    "step_index", "outcome", "started_at", "completed_at", "raw_words", "error_class",
    "received_bytes", "review", "decoded_signals", "interpretation_status",
}
CONTROL_TEXT_FIELDS = (
    "purpose", "source_reference", "address_evidence", "encoding_evidence", "before_value",
    "test_value", "restore_value", "value_unit", "allowed_range_evidence", "stop_conditions",
    "verification_steps", "restore_steps", "host_loss_behavior", "network_loss_behavior",
    "device_restart_behavior", "operator_approval_reference",
)


class Clock:
    def __init__(self):
        self.elapsed = 0.0
        self.origin = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def monotonic(self):
        return self.elapsed

    def now(self):
        return self.origin + timedelta(seconds=self.elapsed)


class CatalogClient:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.values = {4098: (0,), 4099: (173,), 4102: (42,), 28688: (4, 319), 33408: (65526,)}
        self.failure = None
        self.delay = 0.0

    def read_catalog(self, block):
        self.calls.append((block.offset, block.count, self.clock.monotonic()))
        self.clock.elapsed += self.delay
        if self.failure is not None:
            raise self.failure
        return RegisterRead(block.offset, self.values[block.offset])


def complete_draft(**changes):
    return {
        "candidate_id": "control:buffer.start",
        **{field: "Synthetisch, nicht unabhängig geprüft" for field in CONTROL_TEXT_FIELDS},
        "function_code": 6,
        "max_duration_seconds": 30,
        "max_write_requests": 2,
        **changes,
    }


def assert_safe(document, settings, fingerprint=None):
    encoded = json.dumps(document, ensure_ascii=False)
    assert "127.0.0.1" not in encoded
    assert str(settings.data_dir) not in encoded
    assert PRIVATE_ERROR not in encoded
    assert "geheim.sqlite3" not in encoded
    if fingerprint is not None:
        assert fingerprint not in encoded
    private_keys = {
        "target", "target_fingerprint", "configuration_id", "host", "port", "modbus_host",
        "modbus_port", "data_dir", "target_snapshot", "target_host", "target_port",
    }

    def visit(value):
        if isinstance(value, dict):
            assert not private_keys.intersection(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)


def assert_error(response, status, code=None):
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert set(detail) == {"code", "message"}
    assert isinstance(detail["code"], str) and detail["code"]
    assert isinstance(detail["message"], str) and detail["message"]
    if code is not None:
        assert detail["code"] == code
    assert PRIVATE_ERROR not in response.text
    assert "geheim.sqlite3" not in response.text
    return detail


@pytest.fixture
def open_api(tmp_path, monkeypatch):
    @contextmanager
    def opened(*, settings=None, device_client=None):
        if settings is None:
            settings = Settings(
                _env_file=None,
                MODBUS_HOST="127.0.0.1",
                MODBUS_PORT=1502,
                MODBUS_UNIT_ID=255,
                DIAGNOSTICS_SOURCE="simulator",
                COLLECTOR_ENABLED=False,
                COLLECTOR_MAX_REQUESTS=None,
                REGISTER_PROFILE="core",
                DISPLAY_TIMEZONE="UTC",
                DATA_DIR=tmp_path,
            )
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        clock = Clock()
        injected = device_client if device_client is not None else CatalogClient(clock)
        with TestClient(main.app) as http:
            runner = main.app.state.runner
            runner.monotonic = clock.monotonic
            runner.now = clock.now
            runner.client = injected
            yield SimpleNamespace(
                http=http, app=main.app, runner=runner, store=main.app.state.storage,
                settings=settings, clock=clock, device=injected,
            )

    return opened


@pytest.fixture
def api(open_api):
    with open_api() as environment:
        yield environment


def mutate(api, path, body=None, *, method="POST", status=200):
    response = api.http.request(method, f"{BASE}{path}", json=body, headers=HEADERS)
    assert response.status_code == status, response.text
    document = response.json()
    assert_safe(document, api.settings)
    return document


def plan(api, offsets=(4098, 4099, 33408), purpose="Synthetische HTTP-Verbraucherabnahme"):
    return mutate(
        api, "/runs", {"register_ids": [f"register:{offset}" for offset in offsets], "purpose": purpose},
        status=201,
    )


def start(api, run_id):
    return mutate(api, f"/runs/{run_id}/start", {"other_readers_stopped": True})


def read(api, run_id, step):
    return mutate(api, f"/runs/{run_id}/read", {"step_index": step})


def review(api, run_id, step, verdict="continue", observation=None):
    return mutate(api, f"/runs/{run_id}/review", {
        "step_index": step, "verdict": verdict, "observation": observation,
    })


def load(api, path):
    response = api.http.get(f"{BASE}{path}")
    assert response.status_code == 200, response.text
    if path.endswith("/export"):
        assert response.headers["cache-control"] == "private, no-store"
        assert "attachment" in response.headers["content-disposition"]
    document = response.json()
    assert_safe(document, api.settings)
    return document


def seed_history(store):
    store.record_cycle(
        {
            "request_id": "synthetic-core-request",
            "started_at": "2026-10-15T00:00:00+00:00",
            "completed_at": "2026-10-15T00:00:01+00:00",
            "function_code": 3, "unit_id": 255, "offset": 4102,
            "register_count": 1, "outcome": "ok",
        },
        [{
            "observation_id": "synthetic-core-observation", "signal_id": "boiler.temperature",
            "observed_at": "2026-10-15T00:00:01+00:00", "value": 42, "unit": "°C",
            "quality": "ok", "raw_words": [42], "source": "synthetic", "profile_id": "core",
            "profile_version": "1", "decoder_version": "1",
        }],
    )


def assert_monitoring_stopped(api):
    assert api.http.get("/api/collector/status").json()["state"] != "running"


def test_loopback_complete_route_cycle_preserves_raw_evidence_and_minute_history(open_api, tmp_path):
    with ModbusSimulator(catalog=True) as simulator:
        host, port = simulator.address
        settings = Settings(
            _env_file=None, MODBUS_HOST=host, MODBUS_PORT=port, MODBUS_UNIT_ID=255,
            DIAGNOSTICS_SOURCE="simulator", COLLECTOR_ENABLED=False,
            COLLECTOR_MAX_REQUESTS=None, REGISTER_PROFILE="core", DISPLAY_TIMEZONE="UTC",
            DATA_DIR=tmp_path,
        )
        with open_api(settings=settings, device_client=ModbusTcpClient(host, port)) as api:
            seed_history(api.store)
            before = api.http.get("/api/history/boiler.temperature").json()
            created = plan(api)
            run_id = created["run_id"]
            private = api.store.get_diagnostic_run(run_id)["plan"]
            fingerprint = private["target_fingerprint"]
            assert created["state"] == "planned"
            public_plan = created["plan"]
            assert set(public_plan) == PLAN_FIELDS
            assert public_plan["blocks"] == [
                {"offset": 4098, "count": 1}, {"offset": 4099, "count": 1},
                {"offset": 33408, "count": 1},
            ]
            assert public_plan["schema_version"] == 1
            assert public_plan["function_code"] == 3
            assert public_plan["unit_id"] == 255
            assert public_plan["deadline_seconds"] == 3
            assert public_plan["request_budget"] == 3
            assert public_plan["min_interval_seconds"] == 60
            assert public_plan["max_duration_seconds"] == 600
            assert public_plan["stop_conditions"]
            assert_safe(created, settings, fingerprint)
            for path in ("/catalog", "/runs", f"/runs/{run_id}", f"/runs/{run_id}/export"):
                assert_safe(load(api, path), settings, fingerprint)
            assert simulator.received_requests == ()
            opened = start(api, run_id)
            assert opened["state"] == "running"
            assert opened["requests_reserved"] == 0
            assert opened["next_step_index"] == 0
            assert opened["wait_remaining_seconds"] == 60
            assert opened["duration_remaining_seconds"] == 600
            assert simulator.received_requests == ()
            for step, raw in enumerate(([0], [173], [65526])):
                load(api, f"/runs/{run_id}")
                load(api, f"/runs/{run_id}/export")
                load(api, "/catalog")
                assert len(simulator.received_requests) == step
                api.clock.elapsed += 60
                result = read(api, run_id, step)
                assert result["state"] == "awaiting_review"
                assert result["requests_reserved"] == step + 1
                request = result["requests"][step]
                assert set(request) == REQUEST_FIELDS
                assert request["raw_words"] == raw
                assert request["decoded_signals"] == []
                assert request["interpretation_status"] == "raw_only"
                assert request["review"] is None
                assert request["started_at"] and request["completed_at"]
                assert len(simulator.received_requests) == step + 1
                reviewed = review(api, run_id, step, observation="Synthetisch geprüft")
                assert reviewed["state"] == ("completed" if step == 2 else "running")
                assert len(simulator.received_requests) == step + 1
            exported = load(api, f"/runs/{run_id}/export")
            assert exported["plan"] == public_plan
            assert [item["raw_words"] for item in exported["requests"]] == [[0], [173], [65526]]
            assert all(item["review"]["observation"] == "Synthetisch geprüft"
                       for item in exported["requests"])
            assert simulator.received_requests == (
                (255, 3, 4098, 1), (255, 3, 4099, 1), (255, 3, 33408, 1),
            )
            assert api.http.get("/api/history/boiler.temperature").json() == before
            assert api.store.count_observations() == 1
            assert_monitoring_stopped(api)
            counter = plan(api, (28689,))
            counter_id = counter["run_id"]
            assert counter["plan"]["blocks"] == [{"offset": 28688, "count": 2}]
            start(api, counter_id)
            assert len(simulator.received_requests) == 3
            api.clock.elapsed += 60
            answer = read(api, counter_id, 0)["requests"][0]
            assert answer["raw_words"] == [4, 319]
            assert answer["interpretation_status"] == "confirmed_core"
            assert [(signal["signal_id"], signal["value"]) for signal in answer["decoded_signals"]] == [
                ("boiler.operating_minutes", 6079),
            ]
            assert review(api, counter_id, 0)["state"] == "completed"
            assert simulator.received_requests[-1] == (255, 3, 28688, 2)
            assert len(simulator.received_requests) == 4
            assert api.http.get("/api/history/boiler.temperature").json() == before
            assert api.store.count_observations() == 1


def test_catalog_exposes_inventory_without_promoting_raw_or_control_candidates(api):
    catalog = load(api, "/catalog")
    assert set(catalog) == {"catalog_sha256", "source", "blockade", "entries", "control_candidates"}
    assert catalog["catalog_sha256"] == load_catalog().sha256
    assert catalog["source"] == "simulator"
    assert catalog["blockade"] is None
    assert len(catalog["entries"]) == 199
    assert sum(entry["read_support"] == "confirmed_core" for entry in catalog["entries"]) == 5
    assert sum(entry["read_support"] == "documented_raw" for entry in catalog["entries"]) == 194
    for entry in catalog["entries"]:
        assert entry["write_support"] == "unknown"
        assert entry["decoded_value"] is None
        assert entry["latest_diagnostic"] is None
        if entry["read_support"] == "documented_raw":
            assert entry["unit"] is None
    candidates = {candidate["candidate_id"]: candidate for candidate in catalog["control_candidates"]}
    assert set(candidates) == {"control:buffer.start", "control:buffer.target"}
    for candidate_id, (hex_code, offset) in {
        "control:buffer.start": ("9040", 36928), "control:buffer.target": ("9020", 36896),
    }.items():
        assert candidates[candidate_id]["sl_code_hex"] == hex_code
        assert candidates[candidate_id]["potential_offset"] == offset
        assert candidates[candidate_id]["read_block"] is None
        assert candidates[candidate_id]["write_support"] == "unknown"
    assert api.device.calls == []


def test_catalog_latest_response_marks_changed_target_without_disclosing_binding(api):
    run_id = plan(api, (4098,))["run_id"]
    fingerprint = api.store.get_diagnostic_run(run_id)["plan"]["target_fingerprint"]
    start(api, run_id)
    api.clock.elapsed = 60
    read(api, run_id, 0)
    review(api, run_id, 0)
    first = load(api, "/catalog")
    entry = next(item for item in first["entries"] if item["register_id"] == "register:4098")
    latest = entry["latest_diagnostic"]
    assert latest["run_id"] == run_id
    assert latest["source"] == "simulator"
    assert latest["completed_at"]
    assert latest["target_changed"] is False
    assert latest["request"]["raw_words"] == [0]
    api.settings.modbus_port += 1
    changed = load(api, "/catalog")
    latest = next(item for item in changed["entries"]
                  if item["register_id"] == "register:4098")["latest_diagnostic"]
    assert latest["target_changed"] is True
    assert latest["request"]["raw_words"] == [0]
    for document in (changed, load(api, f"/runs/{run_id}"), load(api, f"/runs/{run_id}/export")):
        assert_safe(document, api.settings, fingerprint)
    assert load(api, f"/runs/{run_id}")["target_changed"] is True
    assert len(api.device.calls) == 1


@pytest.mark.parametrize("selection", [
    [], ["register:99999"], ["register:4103"], ["control:buffer.start"],
    ["register:4098", "register:4099", "register:4102", "register:33408"],
    ["register:04098"],
])
def test_invalid_selection_is_rejected_before_any_device_effect(api, selection):
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": selection, "purpose": "Synthetische Negativauswahl",
    })
    assert_error(response, 422, "invalid_selection")
    assert load(api, "/runs")["total"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("selection", [[4098], [True], "register:4098", None])
def test_selection_structure_and_elements_are_strictly_typed(api, selection):
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": selection, "purpose": "Synthetische Typprüfung",
    })
    assert_error(response, 422, "invalid_request")
    assert load(api, "/runs")["total"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("injected", [
    {"host": PRIVATE_ERROR}, {"count": 2}, {"function_code": 6}, {"unit_id": 1},
    {"request_budget": 100}, {"source": "device"}, {"write_address": 36928},
    {"target": {"host": PRIVATE_ERROR, "port": 502}},
])
def test_plan_rejects_transport_and_execution_injection_without_echoing_values(api, injected):
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": ["register:4098"], "purpose": "Synthetisch", **injected,
    })
    assert_error(response, 422)
    assert_safe(response.json(), api.settings)
    assert load(api, "/runs")["total"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("purpose", [None, True, 1, "", " ", "x" * 2001])
def test_plan_purpose_is_required_nonblank_strict_text(api, purpose):
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": ["register:4098"], "purpose": purpose,
    })
    assert_error(response, 422)
    assert api.device.calls == []


@pytest.mark.parametrize("confirmation", [None, False, 1, 1.0, "true", "True", [], {}])
def test_start_requires_literal_boolean_true_without_coercion(api, confirmation):
    run_id = plan(api)["run_id"]
    response = api.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS, json={
        "other_readers_stopped": confirmation,
    })
    assert_error(response, 422)
    assert load(api, f"/runs/{run_id}")["state"] == "planned"
    assert api.device.calls == []


def test_missing_confirmation_and_unknown_start_fields_are_rejected(api):
    run_id = plan(api)["run_id"]
    for body in ({}, {"other_readers_stopped": True, "host": PRIVATE_ERROR}):
        response = api.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS, json=body)
        assert_error(response, 422)
    assert api.device.calls == []


@pytest.mark.parametrize("step", [True, False, "0", 0.0, None, -1])
@pytest.mark.parametrize("action", ["read", "review"])
def test_step_indices_are_strict_nonnegative_integers(api, action, step):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    body = {"step_index": step}
    if action == "review":
        body.update(verdict="continue", observation=None)
    response = api.http.post(f"{BASE}/runs/{run_id}/{action}", headers=HEADERS, json=body)
    assert_error(response, 422)
    assert load(api, f"/runs/{run_id}")["requests_reserved"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("action,body", [
    ("read", {"step_index": 0, "count": 2}),
    ("review", {"step_index": 0, "verdict": "execute", "observation": None}),
    ("review", {"step_index": 0, "verdict": "continue", "observation": 42}),
    ("review", {"step_index": 0, "verdict": "continue", "host": PRIVATE_ERROR}),
    ("stop", {"force": True}),
    ("acknowledge", {"resolution": ""}),
    ("acknowledge", {"resolution": " \t"}),
    ("acknowledge", {"resolution": 42}),
    ("acknowledge", {"resolution": "Synthetisch", "resume": True}),
])
def test_action_bodies_reject_extra_fields_and_invalid_values(api, action, body):
    run_id = plan(api)["run_id"]
    response = api.http.post(f"{BASE}/runs/{run_id}/{action}", headers=HEADERS, json=body)
    assert_error(response, 422)
    assert api.device.calls == []


def test_list_pagination_reports_total_independently_of_page_length(api):
    identifiers = {plan(api, (4098,), purpose=f"Synthetisch {index}")["run_id"] for index in range(5)}
    default = load(api, "/runs")
    assert (default["total"], default["limit"], default["offset"]) == (5, 50, 0)
    first = load(api, "/runs?limit=2&offset=0")
    middle = load(api, "/runs?limit=2&offset=2")
    last = load(api, "/runs?limit=2&offset=4")
    empty = load(api, "/runs?limit=2&offset=5")
    for page, offset, length in ((first, 0, 2), (middle, 2, 2), (last, 4, 1), (empty, 5, 0)):
        assert set(page) == {"total", "limit", "offset", "items"}
        assert (page["total"], page["limit"], page["offset"]) == (5, 2, offset)
        assert len(page["items"]) == length
    assert {item["run_id"] for item in first["items"] + middle["items"] + last["items"]} == identifiers
    assert load(api, "/runs?limit=100&offset=0")["total"] == 5
    for query in ("limit=0", "limit=101", "offset=-1", "limit=1.5", "offset=abc"):
        assert_error(api.http.get(f"{BASE}/runs?{query}"), 422)
    assert api.device.calls == []


def test_read_due_boundary_old_steps_and_reviews_never_replay(api):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 59.999
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 0})
    assert_error(response, 409, "read_not_due")
    assert api.clock.elapsed == 59.999
    assert load(api, f"/runs/{run_id}")["requests_reserved"] == 0
    assert api.device.calls == []
    api.clock.elapsed = 60
    read(api, run_id, 0)
    for step in (0, 1):
        response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": step})
        assert_error(response, 409, "run_conflict")
    first = review(api, run_id, 0, observation="Erste Bewertung")
    response = api.http.post(f"{BASE}/runs/{run_id}/review", headers=HEADERS, json={
        "step_index": 0, "verdict": "anomaly", "observation": "Veralteter Browser",
    })
    assert_error(response, 409, "run_conflict")
    assert load(api, f"/runs/{run_id}")["requests"] == first["requests"]
    api.clock.elapsed = 120
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 0})
    assert_error(response, 409, "run_conflict")
    assert read(api, run_id, 1)["requests_reserved"] == 2
    assert api.device.calls == [(4098, 1, 60), (4099, 1, 120)]


def test_next_interval_includes_transport_and_persistence_time(api, monkeypatch):
    run_id = plan(api)["run_id"]
    finish = api.store.finish_diagnostic_request

    def slow_finish(*args, **kwargs):
        api.clock.elapsed += 17
        return finish(*args, **kwargs)

    monkeypatch.setattr(api.store, "finish_diagnostic_request", slow_finish)
    api.device.delay = 11
    start(api, run_id)
    api.clock.elapsed = 60
    read(api, run_id, 0)
    assert api.clock.elapsed == 88
    review(api, run_id, 0)
    api.clock.elapsed = 147.999
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 1})
    assert_error(response, 409, "read_not_due")
    assert len(api.device.calls) == 1
    api.clock.elapsed = 148
    read(api, run_id, 1)
    assert api.device.calls[1] == (4099, 1, 148)


def test_two_parallel_http_reads_reserve_and_send_once(api):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    barrier = threading.Barrier(2)

    def click():
        barrier.wait(timeout=5)
        return api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 0})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(click) for _ in range(2)]
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_error(next(response for response in responses if response.status_code == 409), 409, "run_conflict")
    reloaded = load(api, f"/runs/{run_id}")
    assert reloaded["requests_reserved"] == 1
    assert len(reloaded["requests"]) == len(api.device.calls) == 1


def test_cancelled_http_consumer_and_reload_cannot_replay_reserved_read(api, monkeypatch):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    entered, release = threading.Event(), threading.Event()
    original = api.device.read_catalog

    def gated(block):
        entered.set()
        assert release.wait(5), "HTTP-Abbruchtest gab den Read nicht frei"
        return original(block)

    monkeypatch.setattr(api.device, "read_catalog", gated)

    async def scenario():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            pending = asyncio.create_task(http.post(
                f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 0},
            ))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                assert api.store.get_diagnostic_run(run_id)["requests_reserved"] == 1
                pending.cancel()
            finally:
                release.set()
            outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
            assert isinstance(outcome, asyncio.CancelledError)
            reloaded = await http.get(f"{BASE}/runs/{run_id}")
            assert reloaded.status_code == 200
            assert reloaded.json()["requests_reserved"] == 1
            duplicate = await http.post(
                f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 0},
            )
            assert_error(duplicate, 409, "run_conflict")

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert len(api.device.calls) == 1
    assert load(api, f"/runs/{run_id}")["requests"][0]["raw_words"] == [0]


def test_deadline_crossed_by_reservation_consumes_budget_without_socket(api, monkeypatch):
    run_id = plan(api)["run_id"]
    reserve = api.store.reserve_diagnostic_request

    def slow_reserve(*args, **kwargs):
        reserve(*args, **kwargs)
        api.clock.elapsed = 600

    monkeypatch.setattr(api.store, "reserve_diagnostic_request", slow_reserve)
    start(api, run_id)
    api.clock.elapsed = 60
    result = read(api, run_id, 0)
    assert result["state"] == "expired"
    assert result["requests_reserved"] == 1
    assert result["requests"][0]["outcome"] != "reserved"
    assert result["requests"][0]["raw_words"] is None
    assert api.device.calls == []
    assert_monitoring_stopped(api)


@pytest.mark.parametrize("hard_error", [False, True])
@pytest.mark.parametrize("termination", ["stop", "deadline"])
def test_stop_and_deadline_during_http_read_preserve_response_and_hard_error(
    api, monkeypatch, hard_error, termination,
):
    run_id = plan(api)["run_id"]
    entered, release = threading.Event(), threading.Event()
    original = api.device.read_catalog

    def gated(block):
        entered.set()
        assert release.wait(5), "Blockierter Read wurde nicht freigegeben"
        if hard_error:
            api.device.failure = ProtocolError(PRIVATE_ERROR, received_bytes=9)
        return original(block)

    monkeypatch.setattr(api.device, "read_catalog", gated)
    start(api, run_id)
    api.clock.elapsed = 60
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(api.http.post, f"{BASE}/runs/{run_id}/read",
                              headers=HEADERS, json={"step_index": 0})
        try:
            assert entered.wait(3)
            if termination == "stop":
                stopping = pool.submit(api.http.post, f"{BASE}/runs/{run_id}/stop", headers=HEADERS)
                assert api.runner.stop_event.wait(3), "HTTP-Stop wartet vor Setzen des Stop-Events"
            else:
                api.clock.elapsed = 600
                assert api.runner.stop_event.wait(3), "Watchdog reagiert nicht auf virtuelle Frist"
        finally:
            release.set()
        answer = reading.result(timeout=5)
        assert answer.status_code == 200, answer.text
        if termination == "stop":
            stopped = stopping.result(timeout=5)
            assert stopped.status_code == 200, stopped.text
    result = load(api, f"/runs/{run_id}")
    expected = "stopped_protocol" if hard_error else ("cancelled" if termination == "stop" else "expired")
    assert result["state"] == expected
    assert result["requests_reserved"] == 1
    assert result["requests"][0]["raw_words"] == (None if hard_error else [0])
    if hard_error:
        assert result["requests"][0]["received_bytes"] == 9
        assert result["requests"][0]["error_class"]
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 1})
    assert_error(response, 409, "run_conflict")
    assert len(api.device.calls) == 1
    assert_monitoring_stopped(api)


@pytest.mark.parametrize("failure,expected", [
    (ModbusConnectionError(PRIVATE_ERROR, received_bytes=0), "stopped_transport"),
    (IncompleteResponseError(PRIVATE_ERROR, received_bytes=4), "stopped_protocol"),
    (ProtocolError(PRIVATE_ERROR, received_bytes=9), "stopped_protocol"),
])
def test_transport_errors_keep_previous_answers_and_never_retry(api, failure, expected):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    first = read(api, run_id, 0)["requests"][0]
    review(api, run_id, 0)
    api.device.failure = failure
    api.clock.elapsed = 120
    result = read(api, run_id, 1)
    assert result["state"] == expected
    assert result["requests"][0]["raw_words"] == first["raw_words"]
    assert result["requests"][1]["received_bytes"] == failure.received_bytes
    assert result["requests"][1]["error_class"]
    assert_safe(result, api.settings)
    for path in (f"/runs/{run_id}", f"/runs/{run_id}/export", "/runs", "/catalog"):
        load(api, path)
    assert len(api.device.calls) == 2
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 2})
    assert_error(response, 409, "run_conflict")
    assert len(api.device.calls) == 2
    assert_monitoring_stopped(api)


def test_data_stop_keeps_invalid_core_raw_words_and_blocks_new_plan_until_acknowledged(api):
    run_id = plan(api, (4102, 33408))["run_id"]
    api.device.values[4102] = (110,)
    start(api, run_id)
    api.clock.elapsed = 60
    result = read(api, run_id, 0)
    assert result["state"] == "stopped_data"
    assert result["requests"][0]["raw_words"] == [110]
    assert load(api, f"/runs/{run_id}/export")["requests"][0]["raw_words"] == [110]
    assert load(api, "/catalog")["blockade"] == "diagnostic_stop_unacknowledged"
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": ["register:4098"], "purpose": "Kein Umgehen des Stopps",
    })
    assert_error(response, 409, "diagnostic_stop_unacknowledged")
    before = deepcopy(result["requests"])
    acknowledged = mutate(api, f"/runs/{run_id}/acknowledge", {"resolution": "Synthetische Ursache geklärt"})
    assert acknowledged["state"] == "stopped_data"
    assert acknowledged["requests"] == before
    assert load(api, "/catalog")["blockade"] is None
    response = api.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                             json={"other_readers_stopped": True})
    assert_error(response, 409, "run_conflict")
    assert plan(api, (4098,))["state"] == "planned"
    assert len(api.device.calls) == 1
    assert api.store.count_observations() == 0
    assert_monitoring_stopped(api)


@pytest.mark.parametrize("verdict,state", [("finish", "cancelled"), ("anomaly", "stopped_data")])
def test_operator_review_changes_state_not_raw_answer_or_network(api, verdict, state):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    answer = read(api, run_id, 0)["requests"][0]
    result = review(api, run_id, 0, verdict, "Synthetische Betreiberbeobachtung")
    assert result["state"] == state
    updated = result["requests"][0]
    assert {key: value for key, value in updated.items() if key != "review"} == {
        key: value for key, value in answer.items() if key != "review"
    }
    assert updated["review"]["verdict"] == verdict
    assert updated["review"]["observation"] == "Synthetische Betreiberbeobachtung"
    assert len(api.device.calls) == 1
    assert_monitoring_stopped(api)


def test_storage_failure_retains_earlier_evidence_and_blocks_further_reads(api, monkeypatch):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    read(api, run_id, 0)
    review(api, run_id, 0)
    api.clock.elapsed = 120

    def broken(*args, **kwargs):
        raise StorageError(PRIVATE_ERROR)

    with monkeypatch.context() as patch:
        patch.setattr(api.store, "finish_diagnostic_request", broken)
        response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 1})
        assert_error(response, 503, "storage_unavailable")
    saved = api.store.get_diagnostic_run(run_id)
    assert saved["requests_reserved"] == 2
    assert saved["requests"][0]["raw_words"] == [0]
    assert saved["requests"][1]["outcome"] == "reserved"
    response = api.http.post(f"{BASE}/runs/{run_id}/read", headers=HEADERS, json={"step_index": 1})
    assert_error(response, 503, "storage_unavailable")
    assert len(api.device.calls) == 2
    assert_monitoring_stopped(api)


@pytest.mark.parametrize("change,code", [
    ("host_missing", "target_not_configured"), ("unit", "target_changed"),
    ("port", "target_changed"), ("catalog", "catalog_changed"),
])
@pytest.mark.parametrize("active", [False, True])
def test_changed_or_invalid_binding_is_rejected_before_socket(api, monkeypatch, change, code, active):
    run_id = plan(api)["run_id"]
    if active:
        start(api, run_id)
        api.clock.elapsed = 60
    if change == "host_missing":
        api.settings.modbus_host = None
    elif change == "unit":
        api.settings.modbus_unit_id = 1
    elif change == "port":
        api.settings.modbus_port += 1
    else:
        catalog = load_catalog()
        changed = type(catalog)(entries=catalog.entries, sha256="0" * 64, metadata=catalog.metadata)
        monkeypatch.setattr("backend.read_checks.load_catalog", lambda: changed)
        monkeypatch.setattr("backend.diagnostics_api.load_catalog", lambda: changed)
    action = "read" if active else "start"
    body = {"step_index": 0} if active else {"other_readers_stopped": True}
    response = api.http.post(f"{BASE}/runs/{run_id}/{action}", headers=HEADERS, json=body)
    assert_error(response, 409, code)
    assert api.store.get_diagnostic_run(run_id)["requests_reserved"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/runs/missing", None), ("GET", "/runs/missing/export", None),
    ("POST", "/runs/missing/start", {"other_readers_stopped": True}),
    ("POST", "/runs/missing/read", {"step_index": 0}),
    ("POST", "/runs/missing/review", {"step_index": 0, "verdict": "continue", "observation": None}),
    ("POST", "/runs/missing/stop", None),
    ("POST", "/runs/missing/acknowledge", {"resolution": "Synthetisch"}),
    ("GET", "/control-plans/missing", None), ("GET", "/control-plans/missing/export", None),
    ("PUT", "/control-plans/missing", {"expected_revision": 1, "draft": complete_draft()}),
])
def test_missing_resource_returns_safe_404(api, method, path, body):
    response = api.http.request(method, f"{BASE}{path}", headers=HEADERS, json=body)
    assert_error(response, 404)
    assert api.device.calls == []


MUTATIONS = [
    ("POST", "/runs", {"register_ids": ["register:4098"], "purpose": "Synthetisch"}),
    ("POST", "/runs/missing/start", {"other_readers_stopped": True}),
    ("POST", "/runs/missing/read", {"step_index": 0}),
    ("POST", "/runs/missing/review", {"step_index": 0, "verdict": "continue", "observation": None}),
    ("POST", "/runs/missing/stop", None),
    ("POST", "/runs/missing/acknowledge", {"resolution": "Synthetisch"}),
    ("POST", "/control-plans", complete_draft()),
    ("PUT", "/control-plans/missing", {"expected_revision": 1, "draft": complete_draft()}),
]


@pytest.mark.parametrize("method,path,body", MUTATIONS)
@pytest.mark.parametrize("headers", [
    {}, {key: value for key, value in HEADERS.items() if key != "Origin"},
    {**HEADERS, "Origin": "http://fremd.invalid"},
    {**HEADERS, "Sec-Fetch-Site": "cross-site"},
    {key: value for key, value in HEADERS.items() if key != "X-Requested-With"},
])
def test_every_new_mutation_enforces_csrf_before_any_effect(api, method, path, body, headers):
    response = api.http.request(method, f"{BASE}{path}", headers=headers, json=body)
    assert response.status_code == 403, response.text
    assert load(api, "/runs")["total"] == 0
    assert load(api, "/control-plans")["items"] == []
    assert api.device.calls == []


def test_valid_same_origin_reaches_domain_validation_not_csrf(api):
    response = api.http.post(f"{BASE}/runs/missing/start", headers=HEADERS,
                             json={"other_readers_stopped": True})
    assert_error(response, 404)
    assert api.device.calls == []


@pytest.mark.parametrize("path", ["/catalog", "/runs"])
def test_catalog_unavailable_is_safe_and_does_not_break_core_history(api, monkeypatch, path):
    seed_history(api.store)
    before = api.http.get("/api/history/boiler.temperature").json()

    def unavailable():
        raise CatalogUnavailable()

    monkeypatch.setattr("backend.diagnostics_api.load_catalog", unavailable)
    if path == "/runs":
        response = api.http.post(f"{BASE}{path}", headers=HEADERS, json={
            "register_ids": ["register:4098"], "purpose": "Synthetisch",
        })
    else:
        response = api.http.get(f"{BASE}{path}")
    assert_error(response, 503, "catalog_unavailable")
    assert api.http.get("/api/history/boiler.temperature").json() == before
    assert api.http.get("/api/health").json() == {"status": "ok", "database": "ok"}
    assert api.device.calls == []


@pytest.mark.parametrize("method,path,store_method,body", [
    ("GET", "/runs", "list_diagnostic_runs", None),
    ("GET", "/runs/missing", "get_diagnostic_run", None),
    ("GET", "/control-plans", "list_control_plans", None),
    ("POST", "/control-plans", "save_control_plan", complete_draft()),
    ("GET", "/control-plans/missing", "get_control_plan", None),
])
def test_storage_errors_use_safe_503_without_exception_or_path(
    api, monkeypatch, method, path, store_method, body,
):
    def broken(*args, **kwargs):
        raise StorageError(PRIVATE_ERROR)

    monkeypatch.setattr(api.store, store_method, broken)
    response = api.http.request(method, f"{BASE}{path}", headers=HEADERS, json=body)
    assert_error(response, 503, "storage_unavailable")
    assert_safe(response.json(), api.settings)
    assert api.device.calls == []


def test_unavailable_app_storage_does_not_leak_internal_details(api, monkeypatch):
    monkeypatch.setattr(api.app.state, "storage", None)
    for path in ("/catalog", "/runs", "/runs/missing/export", "/control-plans"):
        assert_error(api.http.get(f"{BASE}{path}"), 503, "storage_unavailable")
    assert api.device.calls == []


def test_control_complete_revision_cycle_is_offline_and_never_executable(api):
    incomplete = {"candidate_id": "control:buffer.start", "purpose": "Synthetischer Offline-Entwurf"}
    first = mutate(api, "/control-plans", incomplete)
    plan_id = first["plan_id"]
    assert first["revision"] == 1
    assert first["assessment"]["status"] == "draft"
    assert "restore_value" in first["assessment"]["missing_fields"]
    assert first["execution_enabled"] is False
    assert load(api, f"/control-plans/{plan_id}") == first
    assert load(api, "/control-plans") == {"items": [first]}
    draft = complete_draft(before_value="40 synthetisch", test_value="45 synthetisch",
                           restore_value="40 synthetisch")
    second = mutate(api, f"/control-plans/{plan_id}", {"expected_revision": 1, "draft": draft}, method="PUT")
    assert second["revision"] == 2
    assert second["draft"] == draft
    assert second["assessment"]["status"] == "ready_for_review"
    assert second["assessment"]["missing_fields"] == []
    assert second["source_status"] == {"kind": "operator_provided", "independently_verified": False}
    assert second["execution_enabled"] is False
    assert "execution_not_available" in second["assessment"]["blockers"]
    assert "autonomous_fallback_on_host_or_network_loss_unverified" in second["assessment"]["blockers"]
    stale = api.http.put(f"{BASE}/control-plans/{plan_id}", headers=HEADERS, json={
        "expected_revision": 1, "draft": complete_draft(test_value="Veraltete Änderung"),
    })
    assert_error(stale, 409, "revision_conflict")
    assert load(api, f"/control-plans/{plan_id}") == second
    assert api.store.get_control_plan(plan_id, 1) == first
    assert load(api, "/control-plans") == {"items": [second]}
    exported = load(api, f"/control-plans/{plan_id}/export")
    assert exported == second
    assert exported["execution_enabled"] is False
    assert api.http.post(
        f"{BASE}/control-plans/{plan_id}/execute", headers=HEADERS,
    ).status_code in {404, 405}
    assert api.device.calls == []
    assert api.store.count_observations() == 0


def test_two_parallel_control_updates_commit_one_immutable_revision(api):
    first = mutate(api, "/control-plans", complete_draft())
    plan_id = first["plan_id"]
    barrier = threading.Barrier(2)

    def change(value):
        barrier.wait(timeout=5)
        return api.http.put(f"{BASE}/control-plans/{plan_id}", headers=HEADERS, json={
            "expected_revision": 1, "draft": complete_draft(test_value=value),
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(change, value) for value in ("Synthetisch A", "Synthetisch B")]
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert_error(next(response for response in responses if response.status_code == 409), 409, "revision_conflict")
    assert winner["revision"] == 2
    assert load(api, f"/control-plans/{plan_id}") == winner
    assert api.store.get_control_plan(plan_id, 1) == first
    assert api.store.get_control_plan(plan_id, 3) is None
    assert api.device.calls == []


@pytest.mark.parametrize("revision", [None, True, False, 0, -1, "1", 1.0])
def test_control_expected_revision_is_strict_positive_integer(api, revision):
    first = mutate(api, "/control-plans", complete_draft())
    response = api.http.put(f"{BASE}/control-plans/{first['plan_id']}", headers=HEADERS, json={
        "expected_revision": revision, "draft": complete_draft(test_value="Ungültige Revision"),
    })
    assert_error(response, 422)
    assert load(api, f"/control-plans/{first['plan_id']}") == first
    assert api.device.calls == []


@pytest.mark.parametrize("extra", [{"execute": True}, {"host": PRIVATE_ERROR}, {"count": 2}])
@pytest.mark.parametrize("updating", [False, True])
def test_control_models_forbid_injected_execution_fields(api, extra, updating):
    if updating:
        first = mutate(api, "/control-plans", complete_draft())
        response = api.http.put(f"{BASE}/control-plans/{first['plan_id']}", headers=HEADERS, json={
            "expected_revision": 1, "draft": complete_draft(), **extra,
        })
        assert_error(response, 422)
        assert load(api, f"/control-plans/{first['plan_id']}") == first
    else:
        response = api.http.post(f"{BASE}/control-plans", headers=HEADERS, json={**complete_draft(), **extra})
        assert_error(response, 422)
        assert load(api, "/control-plans")["items"] == []
    assert api.device.calls == []


def test_sensor_control_draft_keeps_sensor_blocker_in_export(api):
    created = mutate(api, "/control-plans", complete_draft(candidate_id="register:4102"))
    exported = load(api, f"/control-plans/{created['plan_id']}/export")
    assert exported["assessment"]["status"] == "ready_for_review"
    assert "sensor_value_must_not_be_overridden" in exported["assessment"]["blockers"]
    assert exported["execution_enabled"] is False
    assert api.device.calls == []


@pytest.mark.parametrize("answered", [False, True])
def test_lifespan_recovery_after_reservation_preserves_budget_and_acknowledgement_starts_nothing(
    open_api, monkeypatch, answered,
):
    with open_api() as first:
        run_id = plan(first)["run_id"]
        settings = first.settings
    store = SQLiteStore(settings.data_dir / "monitor.sqlite3")
    store.set_diagnostic_run_state(run_id, "running", None)
    store.reserve_diagnostic_request(run_id, 0, "2026-10-15T00:00:00+00:00")
    if answered:
        store.finish_diagnostic_request(run_id, 0, {
            "outcome": "ok", "raw_words": [0], "decoded": None,
            "error_class": None, "received_bytes": 11,
            "completed_at": "2026-10-15T00:00:01+00:00",
        }, "awaiting_review")
    before = store.get_diagnostic_run(run_id)
    settings.collector_enabled = True
    starts = []
    collector_start = main.Collector.start

    def observed_start(self):
        result = collector_start(self)
        starts.append("started")
        return result

    monkeypatch.setattr("backend.main.Collector.start", observed_start)
    with open_api(settings=settings) as restored:
        result = load(restored, f"/runs/{run_id}")
        assert result["state"] == "interrupted"
        assert result["requests_reserved"] == 1
        assert result["requests"][0]["raw_words"] == ([0] if answered else None)
        assert store.get_diagnostic_run(run_id)["requests"] == before["requests"]
        assert load(restored, "/catalog")["blockade"] == "diagnostic_stop_unacknowledged"
        assert starts == []
        response = restored.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                                      json={"other_readers_stopped": True})
        assert_error(response, 409)
        mutate(restored, f"/runs/{run_id}/acknowledge", {"resolution": "Synthetische Recovery geklärt"})
        assert starts == []
        assert restored.device.calls == []
        assert load(restored, f"/runs/{run_id}")["state"] == "interrupted"
        response = restored.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                                      json={"other_readers_stopped": True})
        assert_error(response, 409, "run_conflict")
        assert plan(restored, (4098,))["state"] == "planned"
        assert starts == []
        assert_monitoring_stopped(restored)


def test_foreign_owner_keeps_reading_api_available_and_never_recovers_foreign_run(open_api, monkeypatch):
    with open_api() as first:
        run_id = plan(first)["run_id"]
        settings = first.settings
    store = SQLiteStore(settings.data_dir / "monitor.sqlite3")
    store.set_diagnostic_run_state(run_id, "running", None)
    store.reserve_diagnostic_request(run_id, 0, "2026-10-15T00:00:00+00:00")
    before = store.get_diagnostic_run(run_id)
    settings.collector_enabled = True
    starts = []
    monkeypatch.setattr("backend.main.Collector.start", lambda self: starts.append("start"))
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    try:
        with open_api(settings=settings) as blocked:
            assert load(blocked, f"/runs/{run_id}")["state"] == "running"
            assert load(blocked, "/catalog")["blockade"] == "run_conflict"
            assert blocked.http.get("/api/history/boiler.temperature").status_code == 200
            assert starts == []
            assert store.get_diagnostic_run(run_id) == before
            response = blocked.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                                         json={"other_readers_stopped": True})
            assert_error(response, 409, "run_conflict")
            assert blocked.device.calls == []
        assert store.get_diagnostic_run(run_id) == before
    finally:
        owner.release()
    assert starts == []


def test_shutdown_cancels_active_run_without_restarting_monitoring(open_api):
    with open_api() as api:
        run_id = plan(api)["run_id"]
        start(api, run_id)
        assert load(api, f"/runs/{run_id}")["state"] == "running"
        settings = api.settings
        store = api.store
    assert store.get_diagnostic_run(run_id)["state"] == "cancelled"
    owner = DeviceLock(settings.data_dir / "collector.lock")
    owner.acquire()
    owner.release()
    assert api.device.calls == []
    with open_api(settings=settings) as reopened:
        assert load(reopened, f"/runs/{run_id}")["state"] == "cancelled"
        assert reopened.device.calls == []
        assert_monitoring_stopped(reopened)


@pytest.mark.parametrize("purpose", ["x", "x" * 2000])
def test_plan_purpose_accepts_both_inclusive_boundaries(api, purpose):
    created = plan(api, (4098,), purpose)
    assert created["plan"]["purpose"] == purpose
    assert api.device.calls == []


def test_selection_is_resolved_deduplicated_and_sorted_without_merging_raw_neighbors(api):
    created = mutate(api, "/runs", {
        "register_ids": ["register:33408", "register:4099", "register:4098", "register:4099"],
        "purpose": "Synthetische unveränderliche Auswahl",
    }, status=201)
    assert created["plan"]["register_ids"] == ["register:4098", "register:4099", "register:33408"]
    assert created["plan"]["blocks"] == [
        {"offset": 4098, "count": 1}, {"offset": 4099, "count": 1},
        {"offset": 33408, "count": 1},
    ]
    assert created["plan"]["request_budget"] == 3
    assert load(api, f"/runs/{created['run_id']}")["plan"] == created["plan"]
    assert api.device.calls == []


@pytest.mark.parametrize("attribute,value,code", [
    ("modbus_host", None, "target_not_configured"),
    ("modbus_unit_id", 1, "target_changed"),
])
def test_invalid_deployment_target_also_blocks_plan_creation(api, attribute, value, code):
    setattr(api.settings, attribute, value)
    response = api.http.post(f"{BASE}/runs", headers=HEADERS, json={
        "register_ids": ["register:4098"], "purpose": "Synthetisch",
    })
    assert_error(response, 409, code)
    assert load(api, "/runs")["total"] == 0
    assert api.device.calls == []


@pytest.mark.parametrize("state", [
    {"state": "stopped_data", "error": PRIVATE_ERROR},
    {"state": "reconnect_wait", "reconnect_attempts": 1},
    {"state": "paused", "reconnect_attempts": 1},
    {"state": "running", "request_in_flight": True},
])
def test_unclean_core_state_blocks_diagnostic_handover_without_overwriting_it(api, state):
    run_id = plan(api)["run_id"]
    api.store.save_collector_state(state, api.clock.now().isoformat())
    response = api.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                             json={"other_readers_stopped": True})
    assert_error(response, 409, "collector_blocked")
    assert api.store.get_collector_state() == state
    assert load(api, f"/runs/{run_id}")["state"] == "planned"
    assert api.device.calls == []


def test_deadline_without_browser_reads_ends_run_and_never_starts_monitoring(api):
    run_id = plan(api)["run_id"]
    start(api, run_id)
    api.clock.elapsed = 600
    assert api.runner.stop_event.wait(3)
    result = load(api, f"/runs/{run_id}")
    assert result["state"] == "expired"
    assert result["requests_reserved"] == 0
    assert result["duration_remaining_seconds"] == 0
    assert api.device.calls == []
    assert_monitoring_stopped(api)


def test_recovery_storage_error_keeps_reading_api_but_prevents_collector_start(open_api, monkeypatch):
    with open_api() as first:
        run_id = plan(first)["run_id"]
        settings = first.settings
    settings.collector_enabled = True
    starts = []

    def broken(self):
        raise StorageError(PRIVATE_ERROR)

    monkeypatch.setattr(SQLiteStore, "interrupt_active_diagnostic_runs", broken)
    monkeypatch.setattr("backend.main.Collector.start", lambda self: starts.append("start"))
    with open_api(settings=settings) as blocked:
        assert load(blocked, f"/runs/{run_id}")["state"] == "planned"
        assert load(blocked, "/catalog")["blockade"] == "storage_unavailable"
        assert blocked.http.get("/api/history/boiler.temperature").status_code == 200
        response = blocked.http.post(f"{BASE}/runs/{run_id}/start", headers=HEADERS,
                                     json={"other_readers_stopped": True})
        assert_error(response, 503, "storage_unavailable")
        assert starts == []
        assert blocked.device.calls == []


def test_broken_catalog_does_not_prevent_real_core_collector_cycle(open_api, monkeypatch):
    with open_api() as first:
        settings = first.settings
    settings.collector_enabled = True
    settings.collector_max_requests = 1
    saved = threading.Event()
    reads = []
    record_cycle = SQLiteStore.record_cycle

    class CoreClient:
        def __init__(self, host, port):
            assert host == "127.0.0.1"

        def read(self, block):
            reads.append((block.offset, block.count))
            return RegisterRead(block.offset, (42,))

    def recorded(self, *args, **kwargs):
        result = record_cycle(self, *args, **kwargs)
        saved.set()
        return result

    def unavailable():
        raise CatalogUnavailable()

    monkeypatch.setattr("backend.collector.ModbusTcpClient", CoreClient)
    monkeypatch.setattr(SQLiteStore, "record_cycle", recorded)
    monkeypatch.setattr("backend.diagnostics_api.load_catalog", unavailable)
    monkeypatch.setattr("backend.read_checks.load_catalog", unavailable)
    with open_api(settings=settings) as api:
        assert saved.wait(3), "Kernsammler wurde durch den Diagnosekatalog gesperrt"
        assert_error(api.http.get(f"{BASE}/catalog"), 503, "catalog_unavailable")
        history = api.http.get("/api/history/boiler.temperature")
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["raw_words"] == [42]
        assert reads == [(4102, 1)]
        assert api.device.calls == []


def test_existing_collector_actions_cannot_bypass_diagnostic_ownership_or_error_ack(
    open_api, monkeypatch,
):
    with open_api() as first:
        settings = first.settings
    settings.collector_enabled = True
    starts = []
    monkeypatch.setattr("backend.main.Collector.start", lambda self: starts.append("start"))
    with open_api(settings=settings) as api:
        assert starts == ["start"]
        run_id = plan(api)["run_id"]
        start(api, run_id)
        for action in ("resume", "acknowledge-and-start"):
            response = api.http.post(f"/api/collector/{action}", headers=HEADERS)
            assert response.status_code == 409, response.text
        assert load(api, f"/runs/{run_id}")["state"] == "running"
        api.clock.elapsed = 60
        read(api, run_id, 0)
        review(api, run_id, 0, "anomaly", "Synthetischer Ursachenstopp")
        for action in ("resume", "acknowledge-and-start"):
            response = api.http.post(f"/api/collector/{action}", headers=HEADERS)
            assert response.status_code == 409, response.text
        assert load(api, f"/runs/{run_id}")["state"] == "stopped_data"
        assert load(api, "/catalog")["blockade"] == "diagnostic_stop_unacknowledged"
        mutate(api, f"/runs/{run_id}/acknowledge", {"resolution": "Synthetisch geklärt"})
        assert starts == ["start"]
        assert len(api.device.calls) == 1
        assert_monitoring_stopped(api)



def test_device_source_and_alias_come_only_from_settings_even_on_loopback(api):
    api.settings.diagnostics_source = "device"
    created = plan(api, (4098,))
    assert created["source"] == created["plan"]["source"] == "device"
    assert created["plan"]["target_alias"] == "Anlage-aktuell"
    assert load(api, "/catalog")["source"] == "device"
    assert api.device.calls == []


def test_completed_budget_cannot_be_reused_by_reload_start_or_extra_step(api):
    run_id = plan(api, (4098,))["run_id"]
    start(api, run_id)
    api.clock.elapsed = 60
    read(api, run_id, 0)
    assert review(api, run_id, 0)["state"] == "completed"
    api.clock.elapsed = 120
    for action, body in (
        ("start", {"other_readers_stopped": True}),
        ("read", {"step_index": 0}), ("read", {"step_index": 1}),
    ):
        response = api.http.post(f"{BASE}/runs/{run_id}/{action}", headers=HEADERS, json=body)
        assert_error(response, 409, "run_conflict")
    reloaded = load(api, f"/runs/{run_id}")
    assert reloaded["requests_reserved"] == 1
    assert reloaded["state"] == "completed"
    assert reloaded["next_step_index"] is None
    assert load(api, f"/runs/{run_id}/export")["requests"][0]["raw_words"] == [0]
    assert len(api.device.calls) == 1
    assert_monitoring_stopped(api)


@pytest.mark.parametrize("field,value", [
    ("function_code", True), ("function_code", "6"), ("max_write_requests", 2.0),
    ("max_write_requests", True), ("max_duration_seconds", True), ("before_value", 42),
    ("host", PRIVATE_ERROR), ("execute", True),
    ("candidate_id", "register:4103"), ("function_code", 0), ("function_code", 128),
    ("max_duration_seconds", 0), ("max_duration_seconds", -1),
    ("max_write_requests", 0), ("max_write_requests", -1),
    *((field, "x" * 4001) for field in CONTROL_TEXT_FIELDS),
])
def test_nested_control_draft_validation_is_strict_and_keeps_previous_revision(api, field, value):
    first = mutate(api, "/control-plans", complete_draft())
    draft = complete_draft()
    draft[field] = value
    response = api.http.put(f"{BASE}/control-plans/{first['plan_id']}", headers=HEADERS, json={
        "expected_revision": 1, "draft": draft,
    })
    assert_error(response, 422)
    assert_safe(response.json(), api.settings)
    assert load(api, f"/control-plans/{first['plan_id']}") == first
    assert api.device.calls == []


def test_latest_evidence_ignores_unread_plans_and_updates_both_core_words(api):
    first_id = plan(api, (28689,))["run_id"]
    start(api, first_id)
    api.clock.elapsed = 60
    read(api, first_id, 0)
    review(api, first_id, 0)
    second_id = plan(api, (28689,))["run_id"]

    def counter_evidence():
        return [item["latest_diagnostic"] for item in load(api, "/catalog")["entries"]
                if item["offset_zero_based"] in (28688, 28689)]

    assert [item["run_id"] for item in counter_evidence()] == [first_id, first_id]
    start(api, second_id)
    api.device.values[28688] = (4, 320)
    api.clock.elapsed = 120
    read(api, second_id, 0)
    review(api, second_id, 0)
    evidence = counter_evidence()
    assert [item["run_id"] for item in evidence] == [second_id, second_id]
    assert [item["request"]["raw_words"] for item in evidence] == [[4, 320], [4, 320]]
    assert [item["request"]["decoded_signals"][0]["value"] for item in evidence] == [6080, 6080]
    assert api.store.count_observations() == 0


def test_saved_control_documents_do_not_revalidate_against_current_catalog(api, monkeypatch):
    created = mutate(api, "/control-plans", complete_draft(candidate_id="register:4102"))

    def unavailable():
        raise CatalogUnavailable()

    monkeypatch.setattr("backend.control_plans.load_catalog", unavailable)
    for path in (f"/control-plans/{created['plan_id']}",
                 f"/control-plans/{created['plan_id']}/export"):
        document = load(api, path)
        assert document == created
    assert load(api, "/control-plans") == {"items": [created]}
    assert api.device.calls == []


@pytest.mark.parametrize("field,value", [
    ("candidate_id", "control:unknown"), ("function_code", 0), ("function_code", 128),
    ("max_duration_seconds", 0), ("max_write_requests", -1),
    *((field, "x" * 4001) for field in CONTROL_TEXT_FIELDS),
])
def test_invalid_control_creation_leaves_no_saved_plan_or_device_effect(api, field, value):
    response = api.http.post(
        f"{BASE}/control-plans", headers=HEADERS, json=complete_draft(**{field: value}),
    )
    assert_error(response, 422)
    assert_safe(response.json(), api.settings)
    assert load(api, "/control-plans") == {"items": []}
    assert api.store.count_observations() == 0
    assert api.device.calls == []


@pytest.mark.parametrize("candidate", ["control:buffer.start", "control:buffer.target"])
def test_operator_fallback_claims_and_blank_evidence_do_not_authorize_control(api, candidate):
    created = mutate(api, "/control-plans", complete_draft(
        candidate_id=candidate, source_reference=" \t ", restore_value=" \n ",
        host_loss_behavior="Betreiber behauptet autonomen Rückfall",
        network_loss_behavior="Betreiber behauptet sicheren Python-Timer",
    ))
    assert created["assessment"]["status"] == "draft"
    assert set(created["assessment"]["missing_fields"]) == {"source_reference", "restore_value"}
    assert created["draft"]["source_reference"] is None
    assert created["draft"]["restore_value"] is None
    exported = load(api, f"/control-plans/{created['plan_id']}/export")
    assert exported == created
    assert exported["source_status"]["independently_verified"] is False
    assert "autonomous_fallback_on_host_or_network_loss_unverified" in exported["assessment"]["blockers"]
    assert exported["execution_enabled"] is False
    assert api.device.calls == []


def test_sensor_blocker_survives_operator_approval_and_revision(api):
    first = mutate(api, "/control-plans", {
        "candidate_id": "register:4102", "purpose": "Synthetische Sensorkanalprüfung",
    })
    second = mutate(api, f"/control-plans/{first['plan_id']}", {
        "expected_revision": 1,
        "draft": complete_draft(
            candidate_id="register:4102",
            operator_approval_reference="Betreiber behauptet Freigabe zum Überschreiben",
        ),
    }, method="PUT")
    assert first["assessment"]["status"] == "draft"
    assert second["assessment"]["status"] == "ready_for_review"
    for document in (first, second, load(api, f"/control-plans/{first['plan_id']}/export")):
        assert "sensor_value_must_not_be_overridden" in document["assessment"]["blockers"]
        assert document["execution_enabled"] is False
    assert api.store.get_control_plan(first["plan_id"], 1) == first
    assert api.device.calls == []


def test_two_parallel_starts_do_not_reset_first_read_deadline_or_budget(api):
    run_id = plan(api, (4098,))["run_id"]
    barrier = threading.Barrier(2)

    def click():
        barrier.wait(timeout=5)
        return api.http.post(
            f"{BASE}/runs/{run_id}/start", headers=HEADERS,
            json={"other_readers_stopped": True},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(click) for _ in range(2)]
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_error(next(response for response in responses if response.status_code == 409), 409, "run_conflict")
    assert load(api, f"/runs/{run_id}")["requests_reserved"] == 0
    assert api.device.calls == []
    api.clock.elapsed = 59.999
    repeated = api.http.post(
        f"{BASE}/runs/{run_id}/start", headers=HEADERS,
        json={"other_readers_stopped": True},
    )
    assert_error(repeated, 409, "run_conflict")
    assert load(api, f"/runs/{run_id}")["requests_reserved"] == 0
    assert api.device.calls == []
    api.clock.elapsed = 60
    assert read(api, run_id, 0)["requests_reserved"] == 1
    assert api.device.calls == [(4098, 1, 60)]
