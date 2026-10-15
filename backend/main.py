from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from backend.collector import Collector
from backend.config import get_settings
from backend.storage import SQLiteStore


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

