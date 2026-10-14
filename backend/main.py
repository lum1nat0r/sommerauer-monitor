from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from backend.config import get_settings
from backend.storage import SQLiteStore


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    application.state.storage = SQLiteStore(settings.data_dir / "monitor.sqlite3")
    yield


app = FastAPI(title="Sommerauer Monitor", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config_summary() -> dict[str, str | int | bool]:
    return get_settings().public_summary()

