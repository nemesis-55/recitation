from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models.schemas import EpisodeRangeGenerateRequest, GenerateRequest
from app.services.episode_queue import run_episode_range_sequential
from app.services.manga_catalog import load_catalog, list_episodes, search_titles
from app.routes.generate import generate_video
from app.services.ops_observer import get_run_detail, list_runs
from app.services.webtoon_catalog_crawler import crawl_webtoon_catalog

router = APIRouter(prefix="/ops", tags=["ops"])

_root = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(_root / "templates"))


@router.get("")
def ops_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="ops_dashboard.html",
        context={"title": "Manga Pipeline Operations Dashboard"},
    )


@router.get("/api/runs")
def runs(limit: int = 30, offset: int = 0, query: Optional[str] = None, status: Optional[str] = None):
    return JSONResponse({"runs": list_runs(limit=limit, offset=offset, query=query, status=status)})


@router.get("/api/runs/{run_path:path}")
def run_detail(run_path: str):
    return JSONResponse(get_run_detail(run_path))


def _resolve_run_root(run_path: str) -> Path:
    root = (settings.output_root / settings.runs_dir_name).resolve()
    candidate = (root / run_path.strip("/")).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=400, detail="Invalid run path")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return candidate


@router.get("/api/runs/{run_path:path}/video")
def run_video(run_path: str):
    run_root = _resolve_run_root(run_path)
    video = run_root / "final" / "video.mp4"
    if not video.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video, media_type="video/mp4")


@router.post("/api/generate")
def generate_from_ops(payload: GenerateRequest):
    return generate_video(payload)


@router.get("/api/manga")
def manga_search(query: Optional[str] = None, genre: Optional[str] = None, limit: int = 50, offset: int = 0):
    return JSONResponse(search_titles(query=query, genre=genre, limit=limit, offset=offset))


@router.get("/api/manga/{title_slug}/episodes")
def manga_episodes(title_slug: str):
    episodes = list_episodes(title_slug)
    return JSONResponse({"title_slug": title_slug, "episodes": episodes, "total": len(episodes)})


@router.get("/api/manga/status")
def manga_status():
    payload = load_catalog()
    return JSONResponse(
        {
            "updated_at": payload.get("updated_at"),
            "stats": payload.get("stats", {}),
            "enabled": settings.webtoon_catalog_enabled,
        }
    )


@router.post("/api/manga/refresh")
def manga_refresh():
    if not settings.webtoon_catalog_enabled:
        raise HTTPException(status_code=400, detail="WEBTOON_CATALOG_ENABLED=false")
    payload = crawl_webtoon_catalog()
    return JSONResponse({"ok": True, "updated_at": payload.get("updated_at"), "stats": payload.get("stats", {})})


@router.post("/api/generate-range")
def generate_range(payload: EpisodeRangeGenerateRequest):
    return run_episode_range_sequential(payload)
