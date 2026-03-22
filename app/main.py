from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.generate import router as generate_router
from app.routes.ops import router as ops_router
from app.services.manga_catalog import catalog_is_stale, load_catalog
from app.services.webtoon_catalog_crawler import crawl_webtoon_catalog
from app.utils.logging_utils import setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.webtoon_catalog_enabled:
        current = load_catalog()
        max_age_hours = settings.webtoon_catalog_refresh_max_age_hours
        if catalog_is_stale(current, max_age_hours=max_age_hours):
            start = time.time()
            logger.info("startup_catalog_refresh begin blocking=true reason=stale max_age_hours=%s", max_age_hours)
            # Blocking refresh by design: app starts serving only after refresh.
            catalog = crawl_webtoon_catalog()
            elapsed = round(time.time() - start, 3)
            logger.info(
                "startup_catalog_refresh done elapsed_sec=%s genres=%s titles=%s episodes=%s",
                elapsed,
                catalog.get("stats", {}).get("genre_count"),
                catalog.get("stats", {}).get("title_count"),
                catalog.get("stats", {}).get("episode_count"),
            )
        else:
            logger.info(
                "startup_catalog_refresh skipped reason=fresh updated_at=%s max_age_hours=%s",
                current.get("updated_at"),
                max_age_hours,
            )
    yield


app = FastAPI(title="Manga Video Pipeline", version="1.0.0", lifespan=lifespan)
app.include_router(generate_router)
app.include_router(ops_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "static")), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
