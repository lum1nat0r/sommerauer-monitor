"""Lesende Diagnoseprojektionen und explizite, endliche Betreiberaktionen."""
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from backend.catalog import (
    CONTROL_CANDIDATES, CatalogSelectionError, CatalogUnavailable, build_read_blocks, load_catalog,
)
from backend.control_plans import ControlPlanAssessment, ControlPlanDraft
from backend.device_lock import DeviceOwnershipError
from backend.read_checks import ReadCheckError, ReadCheckRunner, target_fingerprint
from backend.storage import DIAGNOSTIC_BLOCKING_STATES, RevisionConflict, SQLiteStore, StorageError


ERRORS = {
    "not_found": (404, "Der angeforderte Diagnosebeleg wurde nicht gefunden."),
    "invalid_selection": (422, "Die Auswahl muss ein bis drei gültige Katalogblöcke ergeben."),
    "invalid_request": (422, "Die Nutzdaten entsprechen nicht dem Diagnosevertrag."),
    "target_not_configured": (409, "Für die Diagnose ist kein Ziel konfiguriert."),
    "target_changed": (409, "Die aktuelle Zielkonfiguration passt nicht zum Prüfplan."),
    "catalog_changed": (409, "Der aktuelle Katalog passt nicht zum Prüfplan."),
    "run_conflict": (409, "Der Laufzustand oder Gerätebesitz erlaubt diese Aktion nicht."),
    "read_not_due": (409, "Der Mindestabstand vor der nächsten Anfrage ist noch nicht erreicht."),
    "collector_blocked": (409, "Der Kernsammler muss vor der Diagnose sicher angehalten sein."),
    "diagnostic_stop_unacknowledged": (409, "Ein Diagnosestopp benötigt eine Ursachenquittierung."),
    "revision_conflict": (409, "Der Entwurf wurde inzwischen geändert; aktuelle Revision neu laden."),
    "catalog_unavailable": (503, "Der Registerkatalog ist nicht verfügbar oder ungültig."),
    "storage_unavailable": (503, "Der Diagnosespeicher ist nicht sicher verfügbar."),
}


def api_error(code: str) -> HTTPException:
    status, message = ERRORS[code]
    return HTTPException(status, {"code": code, "message": message})


def install_error_handlers(application: FastAPI) -> None:
    def domain_error(request: Request, exc: Exception):
        code = "storage_unavailable"
        if isinstance(exc, CatalogUnavailable):
            code = "catalog_unavailable"
        elif isinstance(exc, CatalogSelectionError):
            code = "invalid_selection"
        elif isinstance(exc, RevisionConflict):
            code = "revision_conflict"
        elif isinstance(exc, DeviceOwnershipError):
            code = "run_conflict"
        elif isinstance(exc, ReadCheckError):
            code = {
                "unconfigured": "target_not_configured", "invalid_unit": "target_changed",
                "core_blocked": "collector_blocked", "stopped_storage": "storage_unavailable",
                "plan_changed": "target_changed",
            }.get(exc.code, exc.code if exc.code in ERRORS else "run_conflict")
            if exc.code == "plan_changed":
                try:
                    run = _store(request).get_diagnostic_run(request.path_params.get("run_id", ""))
                    if run and run["plan"]["catalog_sha256"] != load_catalog().sha256:
                        code = "catalog_changed"
                except (StorageError, CatalogUnavailable, HTTPException):
                    pass
        error = api_error(code)
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail},
                            headers={"Cache-Control": "private, no-store"})

    async def validation_error(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith("/api/diagnostics/"):
            return await request_validation_exception_handler(request, exc)
        # Pydantic verpackt ValueError aus Feldvalidatoren; keine Input-/ctx-Werte ausgeben.
        unavailable = any(isinstance(item.get("ctx", {}).get("error"), CatalogUnavailable)
                          for item in exc.errors())
        error = api_error("catalog_unavailable" if unavailable else "invalid_request")
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail},
                            headers={"Cache-Control": "private, no-store"})

    for exception in (StorageError, RevisionConflict, CatalogUnavailable, CatalogSelectionError,
                      DeviceOwnershipError, ReadCheckError):
        application.add_exception_handler(exception, domain_error)
    application.add_exception_handler(RequestValidationError, validation_error)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


NonemptyText = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]


class RunCreate(Payload):
    register_ids: list[StrictStr]
    purpose: Annotated[NonemptyText, Field(max_length=2000)]


class RunStart(Payload):
    other_readers_stopped: StrictBool

    @field_validator("other_readers_stopped")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Andere Leser müssen beendet sein.")
        return value


class ReadStep(Payload):
    step_index: Annotated[StrictInt, Field(ge=0)]


class ReviewStep(ReadStep):
    verdict: Literal["continue", "finish", "anomaly"]
    observation: StrictStr | None


class Acknowledge(Payload):
    resolution: NonemptyText


class ControlUpdate(Payload):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    draft: ControlPlanDraft


class ReadBlock(Payload):
    offset: int
    count: int


class PublicPlan(Payload):
    schema_version: Literal[1]
    catalog_sha256: str
    register_ids: list[str]
    blocks: list[ReadBlock]
    purpose: str
    source: Literal["device", "simulator"]
    target_alias: Literal["Anlage-aktuell", "Simulator"]
    function_code: Literal[3]
    unit_id: Literal[255]
    deadline_seconds: Literal[3]
    request_budget: int
    min_interval_seconds: Literal[60]
    max_duration_seconds: Literal[600]
    stop_conditions: list[str]


class DecodedSignal(Payload):
    signal_id: str
    value: int
    unit: str
    offset: int
    raw_words: list[int]
    profile_id: str
    profile_version: str
    decoder_version: str
    source: str


class OperatorReview(Payload):
    verdict: Literal["continue", "finish", "anomaly"]
    observation: str | None


class RequestEvidence(Payload):
    step_index: int
    outcome: str
    started_at: str
    completed_at: str | None
    raw_words: list[int] | None
    error_class: str | None
    received_bytes: int
    review: OperatorReview | None
    decoded_signals: list[DecodedSignal]
    interpretation_status: Literal["confirmed_core", "raw_only"]


class RunDocument(Payload):
    run_id: str
    state: Literal["planned", "running", "awaiting_review", "completed", "cancelled", "expired",
                   "interrupted", "stopped_transport", "stopped_protocol", "stopped_data",
                   "stopped_storage"]
    plan: PublicPlan
    requests_reserved: int
    requests: list[RequestEvidence]
    next_step_index: int | None
    wait_remaining_seconds: float
    duration_remaining_seconds: float
    source: Literal["device", "simulator"]
    target_changed: bool
    created_at: str
    updated_at: str
    started_at: str | None
    ended_at: str | None
    acknowledged_at: str | None
    resolution_note: str | None


class RunPage(Payload):
    total: int
    limit: int
    offset: int
    items: list[RunDocument]


class SourceStatus(Payload):
    kind: Literal["operator_provided"]
    independently_verified: Literal[False]


class ControlDocument(Payload):
    plan_id: str
    revision: int
    created_at: str
    draft: ControlPlanDraft
    source_status: SourceStatus
    assessment: ControlPlanAssessment
    execution_enabled: Literal[False]


class ControlList(Payload):
    items: list[ControlDocument]


class LatestDiagnostic(Payload):
    run_id: str
    completed_at: str
    source: Literal["device", "simulator"]
    target_changed: bool
    request: RequestEvidence


class InventoryEntry(Payload):
    register_id: str
    csv_label: str
    offset_zero_based: int
    sl_code_hex: str
    in_user_reported_imported_profile: bool
    evidence_status: str
    meaning: str | None
    unit: str | None
    decoding: str | None
    read_support: Literal["confirmed_core", "documented_raw"]
    write_support: Literal["unknown"]
    decoded_value: None
    latest_diagnostic: LatestDiagnostic | None


class ControlCandidateDocument(Payload):
    candidate_id: str
    label: str
    sl_code_hex: str
    potential_offset: int
    source: str
    read_block: None
    write_support: Literal["unknown"]
    limitation: str


class CatalogDocument(Payload):
    catalog_sha256: str
    source: Literal["device", "simulator"]
    blockade: str | None
    entries: list[InventoryEntry]
    control_candidates: list[ControlCandidateDocument]


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/api/diagnostics", tags=["Diagnose"],
                   dependencies=[Depends(private_response)])


def _store(request: Request) -> SQLiteStore:
    store = getattr(request.app.state, "storage", None)
    if store is None:
        raise api_error("storage_unavailable")
    return store


def _runner(request: Request) -> ReadCheckRunner:
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise api_error("storage_unavailable")
    return runner


def _startup_guard(request: Request) -> None:
    code = getattr(request.app.state, "diagnostics_blocker", None)
    if code:
        raise api_error(code)


def _require_run(request: Request, run_id: str) -> dict:
    run = _store(request).get_diagnostic_run(run_id)
    if run is None:
        raise api_error("not_found")
    return run


def _public_plan(plan: dict) -> dict:
    result = {key: plan[key] for key in PublicPlan.model_fields if key != "target_alias"}
    result["target_alias"] = "Simulator" if plan["source"] == "simulator" else "Anlage-aktuell"
    return result


def _target_changed(runner: ReadCheckRunner, plan: dict) -> bool:
    # Katalogwechsel separat behandeln: dieses Feld beschreibt ausschließlich das Ziel.
    settings = runner.settings
    return (plan["target"]["host"].casefold() != (settings.modbus_host or "").casefold()
            or plan["target"]["port"] != settings.modbus_port
            or plan["unit_id"] != settings.modbus_unit_id
            or plan["source"] != settings.diagnostics_source)


def _run_document(request: Request, run_id: str) -> dict:
    runner = _runner(request)
    with runner.mode_lock:
        run = _require_run(request, run_id)
        result = runner.status(run_id)
        result.update({key: run[key] for key in (
            "created_at", "updated_at", "started_at", "ended_at", "acknowledged_at", "resolution_note",
        )})
        result["plan"] = _public_plan(run["plan"])
        result["target_changed"] = _target_changed(runner, run["plan"])
        return result


def _control_document(document: dict) -> dict:
    # Nur der gemeinsame Dokumentvertrag, niemals neue SQLite-Spalten durchreichen.
    result = {key: document[key] for key in ControlDocument.model_fields}
    # Beim Speichern validierter Snapshot: GET darf ihn weder neu bewerten noch
    # erneut an den heute verfügbaren Katalog binden. Die Typen bleiben in OpenAPI.
    result["draft"] = ControlPlanDraft.model_construct(**{
        key: document["draft"][key] for key in ControlPlanDraft.model_fields
    })
    result["execution_enabled"] = False
    return result


def _require_control(request: Request, plan_id: str) -> dict:
    document = _store(request).get_control_plan(plan_id)
    if document is None:
        raise api_error("not_found")
    return _control_document(document)


@router.get("/catalog", response_model=CatalogDocument)
def catalog(request: Request) -> dict:
    snapshot = load_catalog()
    runner, store = _runner(request), _store(request)
    latest = {}
    for item in store.latest_diagnostic_results():
        plan, saved = item["plan"], item["request"]
        block = plan["blocks"][saved["step_index"]]
        evidence = ReadCheckRunner.request_evidence(saved)
        entry = {"run_id": item["run_id"], "completed_at": saved["completed_at"],
                 "source": plan["source"], "target_changed": _target_changed(runner, plan),
                 "request": evidence}
        for offset in range(block["offset"], block["offset"] + block["count"]):
            latest[offset] = entry
    return {
        "catalog_sha256": snapshot.sha256, "source": runner.settings.diagnostics_source,
        "blockade": getattr(request.app.state, "diagnostics_blocker", None) or runner.access_blocker(),
        "entries": [{
            **{key: getattr(entry, key) for key in InventoryEntry.model_fields
               if key != "latest_diagnostic"},
            "latest_diagnostic": latest.get(entry.offset_zero_based),
        } for entry in snapshot.entries.values()],
        "control_candidates": [asdict(candidate) for candidate in CONTROL_CANDIDATES.values()],
    }


@router.post("/runs", status_code=201, response_model=RunDocument)
def create_run(payload: RunCreate, request: Request) -> dict:
    runner, store = _runner(request), _store(request)
    with runner.mode_lock:
        _startup_guard(request)
        blocker = runner.access_blocker()
        if blocker:
            raise api_error(blocker)
        settings = runner.settings
        if not settings.modbus_host:
            raise api_error("target_not_configured")
        if settings.modbus_unit_id != 255 or (
            settings.diagnostics_source == "simulator" and settings.modbus_host != "127.0.0.1"
        ):
            raise api_error("target_changed")
        snapshot = load_catalog()
        blocks = build_read_blocks(payload.register_ids)
        plan = {
            "schema_version": 1, "catalog_sha256": snapshot.sha256,
            "register_ids": sorted(set(payload.register_ids), key=lambda value: int(value.split(":")[1])),
            "blocks": [asdict(block) for block in blocks], "purpose": payload.purpose,
            "source": settings.diagnostics_source,
            "target": {"host": settings.modbus_host, "port": settings.modbus_port},
            "target_fingerprint": target_fingerprint(settings, snapshot.sha256),
            "function_code": 3, "unit_id": 255, "deadline_seconds": 3,
            "request_budget": len(blocks), "min_interval_seconds": 60,
            "max_duration_seconds": 600,
            "stop_conditions": ["transport", "protocol", "data", "storage", "operator", "anomaly", "expired"],
        }
        run = store.create_diagnostic_run(plan)
        return _run_document(request, run["run_id"])


@router.get("/runs", response_model=RunPage)
def list_runs(request: Request, limit: int = Query(50, ge=1, le=100),
              offset: int = Query(0, ge=0)) -> dict:
    store = _store(request)
    return {"total": store.count_diagnostic_runs(), "limit": limit, "offset": offset,
            "items": [_run_document(request, run["run_id"])
                      for run in store.list_diagnostic_runs(limit, offset)]}


@router.get("/runs/{run_id}", response_model=RunDocument)
def get_run(run_id: str, request: Request) -> dict:
    return _run_document(request, run_id)


@router.post("/runs/{run_id}/start", response_model=RunDocument)
def start_run(run_id: str, payload: RunStart, request: Request) -> dict:
    _require_run(request, run_id)
    _startup_guard(request)
    runner = _runner(request)
    with runner.mode_lock:
        blocker = runner.access_blocker()
        if blocker:
            raise api_error(blocker)
        runner.start(run_id)
        return _run_document(request, run_id)


@router.post("/runs/{run_id}/read", response_model=RunDocument)
def read_run(run_id: str, payload: ReadStep, request: Request) -> dict:
    _require_run(request, run_id)
    _startup_guard(request)
    _runner(request).read_next(run_id, payload.step_index)
    return _run_document(request, run_id)


@router.post("/runs/{run_id}/review", response_model=RunDocument)
def review_run(run_id: str, payload: ReviewStep, request: Request) -> dict:
    _require_run(request, run_id)
    _startup_guard(request)
    _runner(request).review(run_id, payload.step_index, payload.verdict, payload.observation)
    return _run_document(request, run_id)


@router.post("/runs/{run_id}/stop", response_model=RunDocument)
def stop_run(run_id: str, request: Request, payload: Payload = Body(default=Payload())) -> dict:
    _require_run(request, run_id)
    _startup_guard(request)
    # Niemals außen mode_lock halten: stop() setzt sein Event vor dem Lock-Warten.
    _runner(request).stop(run_id)
    return _run_document(request, run_id)


@router.post("/runs/{run_id}/acknowledge", response_model=RunDocument)
def acknowledge_run(run_id: str, payload: Acknowledge, request: Request) -> dict:
    runner = _runner(request)
    with runner.mode_lock:
        run = _require_run(request, run_id)
        _startup_guard(request)
        if run["state"] not in DIAGNOSTIC_BLOCKING_STATES or run["acknowledged_at"] is not None:
            raise api_error("run_conflict")
        _store(request).acknowledge_diagnostic_run(run_id, payload.resolution)
        return _run_document(request, run_id)


@router.get("/runs/{run_id}/export", response_model=RunDocument)
def export_run(run_id: str, request: Request, response: Response) -> dict:
    response.headers["Content-Disposition"] = 'attachment; filename="diagnostic-run.json"'
    return _run_document(request, run_id)


@router.get("/control-plans", response_model=ControlList)
def list_controls(request: Request) -> dict:
    return {"items": [_control_document(document) for document in _store(request).list_control_plans()]}


@router.post("/control-plans", response_model=ControlDocument)
def create_control(payload: ControlPlanDraft, request: Request) -> dict:
    return _control_document(_store(request).save_control_plan(None, None, payload.model_dump()))


@router.get("/control-plans/{plan_id}", response_model=ControlDocument)
def get_control(plan_id: str, request: Request) -> dict:
    return _require_control(request, plan_id)


@router.put("/control-plans/{plan_id}", response_model=ControlDocument)
def update_control(plan_id: str, payload: ControlUpdate, request: Request) -> dict:
    _require_control(request, plan_id)
    return _control_document(_store(request).save_control_plan(
        plan_id, payload.expected_revision, payload.draft.model_dump(),
    ))


@router.get("/control-plans/{plan_id}/export", response_model=ControlDocument)
def export_control(plan_id: str, request: Request, response: Response) -> dict:
    response.headers["Content-Disposition"] = 'attachment; filename="control-plan.json"'
    return _require_control(request, plan_id)
