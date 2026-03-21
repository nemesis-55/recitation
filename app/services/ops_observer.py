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
            video = child / "final" / "video.mp4"
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
    detail["files"] = {
        "video": str(root / "final" / "video.mp4") if (root / "final" / "video.mp4").exists() else None,
        "subtitles": str(root / "final" / "subtitles.srt") if (root / "final" / "subtitles.srt").exists() else None,
        "timeline": str(root / "meta" / "timeline.json") if (root / "meta" / "timeline.json").exists() else None,
        "report": str(report) if report.exists() else None,
    }
    return detail
