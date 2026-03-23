from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings


def _run_roots() -> list[Path]:
    primary = settings.output_root / settings.runs_dir_name
    return [primary]


def list_runs(limit: int = 30, offset: int = 0, query: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    runs = []
    for root in _run_roots():
        if not root.exists():
            continue
        for report in root.rglob("meta/job_report.json"):
            child = report.parent.parent
            if not child.is_dir():
                continue
            final_dir = child / "final"
            youtube_video = final_dir / "video_youtube.mp4"
            legacy_video = final_dir / "video.mp4"
            video = youtube_video if youtube_video.exists() else legacy_video
            run_key = child.relative_to(root).as_posix()
            item = {
                "run_id": run_key,
                "run_name": child.name,
                "created_at": datetime.fromtimestamp(child.stat().st_mtime).isoformat(timespec="seconds"),
                "has_report": True,
                "has_video": video.exists(),
                "report_path": str(report),
                "video_path": str(video) if video.exists() else None,
                "storage_root": str(root),
            }
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                item["elapsed_sec"] = payload.get("elapsed_sec")
                item["stages"] = list(payload.get("stages", {}).keys())
                item["input"] = payload.get("input", {})
                ve = payload.get("stages", {}).get("video_editor") if isinstance(payload.get("stages"), dict) else None
                if isinstance(ve, dict):
                    item["youtube_video_path"] = ve.get("youtube_video_path")
                    rcp = ve.get("reel_chunk_paths")
                    item["reel_chunk_paths"] = rcp if isinstance(rcp, list) else []
                if payload.get("failed"):
                    item["status"] = "failed"
                    item["failed_stage"] = payload["failed"].get("stage")
                    item["error_code"] = payload["failed"].get("error_code")
                else:
                    item["status"] = "completed" if video.exists() else "in_progress"
                warnings = payload.get("stages", {}).get("quality_checker", {}).get("warnings", [])
                item["warning_count"] = len(warnings) if isinstance(warnings, list) else 0
            except Exception:
                item["report_parse_error"] = True
                item["status"] = "unknown"
            runs.append(item)
    runs.sort(key=lambda r: r["created_at"], reverse=True)
    if query:
        q = query.lower().strip()
        runs = [r for r in runs if q in r.get("run_id", "").lower() or q in str(r.get("input", {}).get("pdf_path", "")).lower()]
    if status:
        wanted = status.lower().strip()
        runs = [r for r in runs if str(r.get("status", "")).lower() == wanted]
    if offset < 0:
        offset = 0
    return runs[offset : offset + max(0, limit)]


def get_run_detail(run_id: str) -> dict[str, Any]:
    root = None
    for candidate_root in _run_roots():
        candidate = candidate_root / run_id.strip("/")
        if candidate.exists():
            root = candidate
            break
    if root is None:
        return {"run_id": run_id, "exists": False}

    report = root / "meta" / "job_report.json"
    detail: dict[str, Any] = {"run_id": run_id, "exists": True, "path": str(root)}
    if report.exists():
        try:
            detail["report"] = json.loads(report.read_text(encoding="utf-8"))
        except Exception as exc:
            detail["report_error"] = str(exc)
    final_dir = root / "final"
    youtube_video = final_dir / "video_youtube.mp4"
    legacy_video = final_dir / "video.mp4"
    selected_video = youtube_video if youtube_video.exists() else legacy_video
    reel_chunks_dir = final_dir / "reels" / "chunks"
    reel_chunks: list[str] = []
    if reel_chunks_dir.is_dir():
        reel_chunks = sorted(str(p) for p in reel_chunks_dir.glob("reel_chunk_*.mp4"))
    reel_master = final_dir / "video_reel.mp4"
    detail["files"] = {
        "video": str(selected_video) if selected_video.exists() else None,
        "youtube_video": str(youtube_video) if youtube_video.exists() else None,
        "reel_video": str(reel_master) if reel_master.exists() else None,
        "reel_chunks": reel_chunks,
        "subtitles": str(final_dir / "subtitles.srt") if (final_dir / "subtitles.srt").exists() else None,
        "timeline": str(root / "meta" / "timeline.json") if (root / "meta" / "timeline.json").exists() else None,
        "report": str(report) if report.exists() else None,
    }
    return detail
