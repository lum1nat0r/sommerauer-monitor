from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from backend.collector import Collector, CollectorStopped
from backend.config import get_settings
from backend.logging_config import (
    MAX_REQUEST_BYTES, LoggingConfigError, export_configuration, import_configuration, merge_csv,
)
from backend.registers import CONTROL_CANDIDATES, SIGNAL_DEFINITIONS
from backend.storage import LoggingConfigConflict, SQLiteStore, StorageError, utc_now


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    storage = SQLiteStore(settings.data_dir / "monitor.sqlite3")
    application.state.storage = storage
    collector = None
    if settings.collector_enabled:
        collector = Collector(
            host=settings.modbus_host,
            port=settings.modbus_port,
            store=storage,
            data_dir=settings.data_dir,
            max_requests=settings.collector_max_requests,
            retry_on_transport_error=settings.collector_max_requests is None,
        )
        collector.start()
    application.state.collector = collector
    try:
        yield
    finally:
        if collector is not None:
            collector.stop()


app = FastAPI(title="Sommerauer Monitor", version="0.3.1", lifespan=lifespan)


class AppConfigUpdate(BaseModel):
    display_timezone: str = Field(min_length=1, max_length=100)


def _storage(request: Request) -> SQLiteStore:
    storage = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(503, "Datenbank ist nicht verfügbar.")
    return storage


def _parse_time(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(422, f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    start_utc, end_utc = _parse_time(start, "start"), _parse_time(end, "end")
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise HTTPException(422, "start must be earlier than end")
    return start_utc, end_utc


@app.middleware("http")
async def protect_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        requested_with = request.headers.get("x-requested-with")
        public_origin = get_settings().public_origin
        allowed_origins = {str(request.base_url).rstrip("/")}
        if public_origin is not None:
            # Explizite Deploymentfreigabe statt ungeprüfter Forwarded-Header.
            allowed_origins.add(str(public_origin).rstrip("/"))
        if (
            not origin
            or origin.rstrip("/") not in allowed_origins
            or fetch_site == "cross-site"
            or requested_with != "SommerauerMonitor"
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=403, content={"detail": "Anfrage aus derselben Herkunft mit gültigem Anwendungskopf erforderlich."})
    return await call_next(request)



@app.get("/api/version")
def version_info() -> dict[str, str]:
    return {
        "version": os.environ.get("APP_VERSION", app.version),
        "revision": os.environ.get("BUILD_REVISION", "unknown"),
    }

@app.get("/api/health")
def health(request: Request) -> dict[str, object]:
    storage = getattr(request.app.state, "storage", None)
    database_ok = storage.database_health() if storage is not None else False
    return {"status": "ok" if database_ok else "degraded", "database": "ok" if database_ok else "unavailable"}


@app.get("/api/config")
def config_summary(request: Request) -> dict[str, object]:
    summary: dict[str, object] = get_settings().public_summary()
    storage = getattr(request.app.state, "storage", None)
    if storage is not None:
        try:
            saved = storage.latest_config()
        except StorageError:
            saved = None
        if saved is not None:
            summary["display_timezone"] = saved["display_timezone"]
    return summary


@app.put("/api/config")
def update_config(payload: AppConfigUpdate, request: Request) -> dict[str, object]:
    settings = get_settings()
    try:
        # Reuse the installed-zone validation; no host, port, token, or path is writable here.
        updated = settings.model_copy(update={"display_timezone": payload.display_timezone})
        updated = type(settings).model_validate(updated.model_dump(by_alias=True))
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, "Invalid application configuration") from exc
    storage = _storage(request)
    saved = {
        "display_timezone": updated.display_timezone,
        "collector_enabled": settings.collector_enabled,
        "register_profile": settings.register_profile,
    }
    try:
        storage.save_config(storage.next_config_version(), saved, utc_now())
        storage.record_event(
            str(uuid4()), utc_now(), "configuration_changed", "info",
            "Application configuration changed", {"fields": ["display_timezone"]},
        )
    except StorageError as exc:
        raise HTTPException(503, "Configuration could not be saved") from exc
    return {"display_timezone": updated.display_timezone}


async def _logging_payload(request: Request, content_field: str) -> dict[str, object]:
    # Begrenztes Streaming verhindert, dass schon das JSON-Lesen beliebig viel RAM belegt.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Die Aufzeichnungskonfiguration darf höchstens 4 MiB groß sein.")
        body.extend(chunk)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Die Anfrage muss gültiges JSON enthalten.") from exc
    if not isinstance(payload, dict) or set(payload) != {"revision", content_field}:
        raise HTTPException(422, f"Die Anfrage benötigt genau revision und {content_field}.")
    if type(payload["revision"]) is not int or payload["revision"] < 0:
        raise HTTPException(422, "Die Revision muss eine nichtnegative ganze Zahl sein.")
    return payload


def _logging_config_response(
    request: Request, snapshot: dict[str, object], draft: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    collector = getattr(request.app.state, "collector", None)
    status = collector.logging_status(saved_revision=snapshot["revision"]) if collector is not None else {
        "active_revision": snapshot["revision"],
        "active_entries": snapshot["entries"],
        "apply_status": "inaktiv",
    }
    return {
        "revision": snapshot["revision"],
        "entries": snapshot["entries"] if draft is None else draft,
        "active_revision": status["active_revision"],
        "active_entries": status["active_entries"],
        "apply_status": status["apply_status"],
    }


@app.get("/api/signals")
def signal_definitions() -> dict[str, object]:
    return {
        "signals": [
            {"signal_id": signal_id, **definition}
            for signal_id, definition in SIGNAL_DEFINITIONS.items()
        ],
        "control_candidates": CONTROL_CANDIDATES,
    }


@app.get("/api/logging-config")
def logging_config(request: Request) -> dict[str, object]:
    try:
        return _logging_config_response(request, _storage(request).get_logging_config())
    except StorageError as exc:
        raise HTTPException(503, "Die Aufzeichnungskonfiguration ist nicht verfügbar.") from exc


@app.get("/api/logging-config/export")
def export_logging_config(request: Request) -> Response:
    try:
        snapshot = _storage(request).get_logging_config()
        content = export_configuration(snapshot["entries"])
        return Response(content, media_type="application/json", headers={
            "Content-Disposition": 'attachment; filename="sommerauer-aufzeichnung.json"',
            "Cache-Control": "no-store",
        })
    except LoggingConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(503, "Die Aufzeichnungskonfiguration ist nicht verfügbar.") from exc


@app.post("/api/logging-config/import-preview")
async def import_logging_config(request: Request) -> dict[str, object]:
    payload = await _logging_payload(request, "configuration")
    try:
        snapshot = _storage(request).get_logging_config()
        if payload["revision"] != snapshot["revision"]:
            raise LoggingConfigConflict("Die Aufzeichnungskonfiguration wurde zwischenzeitlich geändert. Bitte neu laden und den Import erneut prüfen.")
        draft = import_configuration(payload["configuration"], snapshot["entries"])
        return _logging_config_response(request, snapshot, draft)
    except LoggingConfigConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LoggingConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(503, "Die Aufzeichnungskonfiguration ist nicht verfügbar.") from exc


@app.post("/api/logging-config/preview")
async def preview_logging_config(request: Request) -> dict[str, object]:
    payload = await _logging_payload(request, "csv_text")
    try:
        snapshot = _storage(request).get_logging_config()
        if payload["revision"] != snapshot["revision"]:
            raise LoggingConfigConflict("Die Aufzeichnungskonfiguration wurde zwischenzeitlich geändert. Bitte neu laden und den Import erneut prüfen.")
        draft = merge_csv(snapshot["entries"], payload["csv_text"])
        return _logging_config_response(request, snapshot, draft)
    except LoggingConfigConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LoggingConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(503, "Die Aufzeichnungskonfiguration ist nicht verfügbar.") from exc


@app.put("/api/logging-config")
async def update_logging_config(request: Request) -> dict[str, object]:
    payload = await _logging_payload(request, "entries")
    try:
        snapshot = _storage(request).save_logging_config(payload["revision"], payload["entries"])
        return _logging_config_response(request, snapshot)
    except LoggingConfigConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LoggingConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(503, "Die Aufzeichnungskonfiguration konnte nicht gespeichert werden.") from exc


@app.get("/api/signals/current")
def current_signals(request: Request) -> dict[str, object]:
    storage = _storage(request)
    now = datetime.now(timezone.utc)
    result = []
    try:
        for row in storage.current_signals():
            measured = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
            age = max(0.0, (now - measured).total_seconds())
            fresh_until_age_seconds = 4 * SIGNAL_DEFINITIONS.get(row["signal_id"], {}).get("interval_seconds", 60)
            result.append({
                "signal_id": row["signal_id"], "value": row["value"], "unit": row["unit"],
                "observed_at": row["observed_at"], "age_seconds": age,
                "quality": row["quality"],
                "error_code": row["error_code"], "error_message": row["error_message"],
                "block_offset": row["block_offset"], "register_count": row["register_count"],
                "fresh_until_age_seconds": fresh_until_age_seconds,
                "fresh": age <= fresh_until_age_seconds and row["quality"] == "ok" and row["value"] is not None,
            })
    except (StorageError, ValueError) as exc:
        raise HTTPException(503, "Signal data unavailable") from exc
    return {"signals": result, "as_of": now.isoformat()}


@app.get("/api/history/{signal_id}")
def history(
    signal_id: str,
    request: Request,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10_000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    if signal_id not in SIGNAL_DEFINITIONS:
        raise HTTPException(404, "Unknown signal")
    start_utc, end_utc = _range(start, end)
    storage = _storage(request)
    try:
        total = storage.count_observations(signal_id=signal_id, start=start_utc, end=end_utc)
        rows = storage.history_page(signal_id, start_utc, end_utc, limit=limit, offset=offset)
    except StorageError as exc:
        raise HTTPException(503, "History unavailable") from exc
    return {"signal_id": signal_id, "total": total, "limit": limit, "offset": offset, "items": rows}


@app.get("/api/events")
def events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    storage = _storage(request)
    try:
        return {"total": storage.count_events(), "limit": limit, "offset": offset,
                "items": storage.events(limit=limit, offset=offset)}
    except StorageError as exc:
        raise HTTPException(503, "Events unavailable") from exc


@app.get("/api/export.csv")
def export_csv(
    request: Request,
    start: str | None = None,
    end: str | None = None,
) -> StreamingResponse:
    start_utc, end_utc = _range(start, end)
    storage = _storage(request)

    def rows() -> Iterator[str]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow([
            "observed_at", "observation_id", "signal_id", "value", "unit",
            "quality", "raw_words", "source", "profile_id", "profile_version", "decoder_version",
            "error_code", "error_message",
        ])
        yield buffer.getvalue()
        for item in storage.stream_observations(start=start_utc, end=end_utc):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([
                item["observed_at"], item["observation_id"], item["signal_id"], item["value"],
                item["unit"], item["quality"], json.dumps(item["raw_words"], separators=(",", ":")),
                item["source"], item["profile_id"], item["profile_version"], item["decoder_version"],
                item["error_code"], item["error_message"],
            ])
            yield buffer.getvalue()

    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="measurements.csv"'})


@app.get("/api/collector/status")
def collector_status(request: Request) -> dict[str, object]:
    collector = getattr(request.app.state, "collector", None)
    if collector is not None:
        return collector.status()
    storage = getattr(request.app.state, "storage", None)
    try:
        saved = storage.get_collector_state() if storage is not None else None
    except StorageError:
        saved = {}
    if saved is None:
        return {
            "state": "unconfigured", "reason": None, "reconnect_attempts": 0,
            "next_action_at": None,
            "next_action": "Configure and start collection", "profile_id": "core",
        }
    if not isinstance(saved, dict):
        saved = {}
    reasons = {
        "running": "Erfassung läuft",
        "reconnect_wait": "Verbindungsfehler; Abfragen laufen im regulären Intervall weiter",
        "stopped_transport": "Transportfehler; Erfassung angehalten",
        "stopped_protocol": "Protokollfehler; Erfassung angehalten",
        "stopped_data": "Datenfehler; Erfassung angehalten",
        "stopped_storage": "Speicher- oder Zustandsfehler; Erfassung angehalten",
        "paused": "Erfassung pausiert",
        "completed": "Erfassung abgeschlossen",
    }
    state = saved.get("state")
    attempts = saved.get("reconnect_attempts", 0)
    if not isinstance(state, str) or state not in reasons or isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        state, attempts = "stopped_storage", 0
    return {
        "state": state, "reason": reasons.get(state) if saved.get("error") or state == "stopped_storage" else None,
        "reconnect_attempts": attempts,
        "next_action_at": saved.get("retry_at") if isinstance(saved.get("retry_at"), str) else None,
        "next_action": saved.get("next_action") if isinstance(saved.get("next_action"), str) else "Inspect persisted state; no automatic reads",
        "profile_id": "core",
    }


def _collector(request: Request) -> Collector:
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        raise HTTPException(409, "Collector is not configured")
    return collector


@app.post("/api/collector/pause")
def pause_collector(request: Request) -> dict[str, object]:
    collector = _collector(request)
    collector.pause()
    return collector.status()


@app.post("/api/collector/resume")
def resume_collector(request: Request) -> dict[str, object]:
    collector = _collector(request)
    try:
        collector.resume()
    except CollectorStopped as exc:
        raise HTTPException(409, "Collector must be acknowledged after resolving its cause") from exc
    return collector.status()


@app.post("/api/collector/acknowledge-and-start")
def acknowledge_collector(request: Request) -> dict[str, object]:
    collector = _collector(request)
    try:
        collector.acknowledge_and_start()
    except CollectorStopped as exc:
        raise HTTPException(409, "Collector cannot be acknowledged in its current state") from exc
    return collector.status()

static_directory = Path(__file__).resolve().parent.parent / "static"
if static_directory.is_dir():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
