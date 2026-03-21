from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models.schemas import GenerateRequest
from app.routes.generate import generate_video
from app.services.ops_observer import get_run_detail, list_runs

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
