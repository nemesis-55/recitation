from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.generate import router as generate_router
from app.routes.ops import router as ops_router
from app.utils.logging_utils import setup_logging

setup_logging(settings.log_level)

app = FastAPI(title="Manga Video Pipeline", version="1.0.0")
app.include_router(generate_router)
app.include_router(ops_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "static")), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
