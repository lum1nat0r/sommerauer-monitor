from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from backend.collector import Collector
from backend.config import get_settings
from backend.storage import SQLiteStore, StorageError


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



@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config_summary() -> dict[str, str | int | bool]:
    return get_settings().public_summary()



@app.get("/api/collector/status")
def collector_status() -> dict[str, object]:
    collector = getattr(app.state, "collector", None)
    if collector is not None:
        return collector.status()
    storage = getattr(app.state, "storage", None)
    try:
        saved = storage.get_collector_state() if storage is not None else None
    except StorageError:
        saved = {}
    if saved is None:
        return {
            "state": "unconfigured",
            "reason": None,
            "reconnect_attempts": 0,
            "reconnect_attempt_limit": 5,
            "next_action_at": None,
            "next_action": "Configure and start collection",
            "profile_id": "core",
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
    if (
        not isinstance(state, str)
        or state not in reasons
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 0 <= attempts <= 5
    ):
        state = "stopped_storage"
        attempts = 0
    return {
        "state": state,
        "reason": reasons.get(state) if saved.get("error") or state == "stopped_storage" else None,
        "reconnect_attempts": attempts,
        "reconnect_attempt_limit": 5,
        "next_action_at": saved.get("retry_at") if isinstance(saved.get("retry_at"), str) else None,
        "next_action": saved.get("next_action") if isinstance(saved.get("next_action"), str) else "Inspect persisted state; no automatic reads",
        "profile_id": "core",
    }
