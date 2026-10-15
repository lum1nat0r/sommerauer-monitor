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
from starlette.concurrency import run_in_threadpool

from backend.collector import Collector, CollectorStopped
from backend.config import get_settings
from backend.device_lock import DeviceOwnershipError
from backend.diagnostics_api import api_error, install_error_handlers, router as diagnostics_router
from backend.read_checks import ReadCheckError, ReadCheckRunner
from backend.storage import SQLiteStore, StorageError, utc_now


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = await run_in_threadpool(get_settings)
    storage = await run_in_threadpool(SQLiteStore, settings.data_dir / "monitor.sqlite3")
    application.state.storage = storage
    collector = None
    if settings.collector_enabled:
        collector = await run_in_threadpool(
            Collector,
            host=settings.modbus_host,
            port=settings.modbus_port,
            store=storage,
            data_dir=settings.data_dir,
            max_requests=settings.collector_max_requests,
            retry_on_transport_error=settings.collector_max_requests is None,
        )
    application.state.collector = collector
    runner = await run_in_threadpool(
        ReadCheckRunner, settings=settings, store=storage, collector=collector,
    )
    application.state.runner = runner
    application.state.diagnostics_blocker = None
    application.state.collector_started = False
    try:
        try:
            await run_in_threadpool(runner.recover_interrupted)
        except DeviceOwnershipError:
            application.state.diagnostics_blocker = "run_conflict"
        except ReadCheckError as exc:
            application.state.diagnostics_blocker = (
                "storage_unavailable" if exc.code == "stopped_storage" else "run_conflict"
            )
        except (StorageError, OSError):
            application.state.diagnostics_blocker = "storage_unavailable"
        if collector is not None and application.state.diagnostics_blocker is None:
            try:
                await run_in_threadpool(collector.start)
                application.state.collector_started = True
            except DeviceOwnershipError:
                application.state.diagnostics_blocker = "run_conflict"
            except CollectorStopped:
                # Persistente Diagnosestopps bleiben quittierbar, ohne Autostart.
                pass
            except (StorageError, OSError):
                application.state.diagnostics_blocker = "storage_unavailable"
        yield
    finally:
        try:
            await run_in_threadpool(runner.close)
        finally:
            # Bei fremdem Besitz auch beim Shutdown keinen fremden Zustand ändern.
            if collector is not None and application.state.collector_started:
                await run_in_threadpool(collector.stop)


app = FastAPI(title="Sommerauer Monitor", version="0.2.1", lifespan=lifespan)

install_error_handlers(app)
app.include_router(diagnostics_router)

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
    settings = get_settings()
    summary: dict[str, object] = settings.public_summary()
    summary["diagnostics_source"] = settings.diagnostics_source
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
        "completed": "Erfassung abgeschlossen",
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
        raise api_error("collector_blocked")
    return collector


def _collector_action(request: Request, action: str) -> dict[str, object]:
    runner = request.app.state.runner
    with runner.mode_lock:
        try:
            blocker = request.app.state.diagnostics_blocker or runner.access_blocker()
            if blocker is not None:
                raise api_error(blocker)
            collector = _collector(request)
            getattr(collector, action)()
            if action in {"resume", "acknowledge_and_start"}:
                request.app.state.collector_started = True
        except DeviceOwnershipError:
            request.app.state.diagnostics_blocker = "run_conflict"
            raise api_error("run_conflict") from None
        except CollectorStopped:
            raise api_error(runner.access_blocker() or "collector_blocked") from None
        except (StorageError, OSError):
            request.app.state.diagnostics_blocker = "storage_unavailable"
            raise api_error("storage_unavailable") from None
        return collector.status()


@app.post("/api/collector/pause")
def pause_collector(request: Request) -> dict[str, object]:
    return _collector_action(request, "pause")


@app.post("/api/collector/resume")
def resume_collector(request: Request) -> dict[str, object]:
    return _collector_action(request, "resume")


@app.post("/api/collector/acknowledge-and-start")
def acknowledge_collector(request: Request) -> dict[str, object]:
    return _collector_action(request, "acknowledge_and_start")

static_directory = Path(__file__).resolve().parent.parent / "static"
if static_directory.is_dir():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
