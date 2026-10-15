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
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from backend.collector import Collector, CollectorStopped
from backend.config import get_settings
from backend.storage import SQLiteStore, StorageError, utc_now


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
        )
        collector.start()
    application.state.collector = collector
    try:
        yield
    finally:
        if collector is not None:
            collector.stop()


app = FastAPI(title="Sommerauer Monitor", version="0.1.0", lifespan=lifespan)


class AppConfigUpdate(BaseModel):
    display_timezone: str = Field(min_length=1, max_length=100)


def _storage(request: Request) -> SQLiteStore:
    storage = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(503, "Database is unavailable")
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
        if (
            not origin
            or origin.rstrip("/") != str(request.base_url).rstrip("/")
            or fetch_site == "cross-site"
            or requested_with != "SommerauerMonitor"
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=403, content={"detail": "Same-origin request required"})
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


@app.get("/api/signals/current")
def current_signals(request: Request) -> dict[str, object]:
    storage = _storage(request)
    now = datetime.now(timezone.utc)
    result = []
    try:
        for row in storage.current_signals():
            measured = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
            age = max(0.0, (now - measured).total_seconds())
            result.append({
                "signal_id": row["signal_id"], "value": row["value"], "unit": row["unit"],
                "observed_at": row["observed_at"], "age_seconds": age,
                "quality": row["quality"], "fresh": age <= 120 and row["quality"] == "ok",
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
    if signal_id not in {
        "boiler.temperature", "buffer.top_temperature",
        "buffer.bottom_temperature", "boiler.operating_minutes",
    }:
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
        ])
        yield buffer.getvalue()
        for item in storage.stream_observations(start=start_utc, end=end_utc):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([
                item["observed_at"], item["observation_id"], item["signal_id"], item["value"],
                item["unit"], item["quality"], json.dumps(item["raw_words"], separators=(",", ":")),
                item["source"], item["profile_id"], item["profile_version"], item["decoder_version"],
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
            "reconnect_attempt_limit": 5, "next_action_at": None,
            "next_action": "Configure and start collection", "profile_id": "core",
        }
    if not isinstance(saved, dict):
        saved = {}
    reasons = {
        "running": "Wiederaufnahme erfolgreich; Budget-Reset nach drei Kernzyklen",
        "reconnect_wait": "Verbindungsfehler; begrenzte Wiederaufnahme geplant",
        "stopped_transport": "Wiederaufnahmebudget ausgeschöpft",
        "stopped_protocol": "Protokollfehler; Erfassung angehalten",
        "stopped_data": "Datenfehler; Erfassung angehalten",
        "stopped_storage": "Speicher- oder Zustandsfehler; Erfassung angehalten",
        "paused": "Erfassung pausiert",
    }
    state = saved.get("state")
    attempts = saved.get("reconnect_attempts", 0)
    if not isinstance(state, str) or state not in reasons or isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 5:
        state, attempts = "stopped_storage", 0
    return {
        "state": state, "reason": reasons.get(state) if saved.get("error") or state == "stopped_storage" else None,
        "reconnect_attempts": attempts, "reconnect_attempt_limit": 5,
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
