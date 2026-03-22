from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.config import settings


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "unknown"


def derive_run_path_from_source(source_path: str) -> str | None:
    try:
        parsed = urlparse(source_path)
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in {"http", "https"} or "webtoons.com" not in host:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    # Typical: /en/romance/dirty-deeds/episode-1/viewer
    # Some links can omit/replace the episode slug and only include `episode_no` query.
    # Keep folder layout stable: <genre>/<title>/<episode>.
    if len(parts) >= 3:
        offset = 1 if parts[0].lower() in {"en", "es", "fr", "de", "id", "th", "zh-hant"} else 0
        if len(parts) > offset + 2:
            genre = _slug(parts[offset])
            title = _slug(parts[offset + 1])
            episode_part = parts[offset + 2]
            episode = _slug(episode_part)
            if episode in {"list", "viewer", "episode"}:
                q = parse_qs(parsed.query or "")
                ep_no = (q.get("episode_no") or [""])[0].strip()
                if ep_no.isdigit():
                    episode = f"ep-{int(ep_no)}"
                else:
                    episode = "episode-unknown"
            return f"{genre}/{title}/{episode}"
    if len(parts) >= 2:
        genre = _slug(parts[-2])
        title = _slug(parts[-1])
        q = parse_qs(parsed.query or "")
        ep_no = (q.get("episode_no") or [""])[0].strip()
        episode = f"ep-{int(ep_no)}" if ep_no.isdigit() else "episode-unknown"
        return f"{genre}/{title}/{episode}"
    return None


def _resolve_unique_run_path(base_dir: Path, run_relpath: str) -> Path:
    parts = [p for p in run_relpath.split("/") if p]
    if not parts:
        parts = [str(uuid.uuid4())]
    parent = ensure_dir(base_dir.joinpath(*parts[:-1])) if len(parts) > 1 else base_dir
    leaf = parts[-1]
    target = parent / leaf
    if not target.exists():
        return target
    counter = 2
    while True:
        candidate = parent / f"{leaf}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def create_run_dirs(job_id: str | None = None) -> dict[str, Path]:
    run_id = (job_id or str(uuid.uuid4())).strip("/")
    runs_root = ensure_dir(settings.output_root / settings.runs_dir_name)
    root = ensure_dir(_resolve_unique_run_path(runs_root, run_id))
    dirs = {
        "root": root,
        "pages": ensure_dir(root / "pages"),
        "panels": ensure_dir(root / "panels"),
        "audio": ensure_dir(root / "audio"),
        "clips": ensure_dir(root / "clips"),
        "final": ensure_dir(root / "final"),
        "meta": ensure_dir(root / "meta"),
    }
    return dirs


# Backward compatibility alias for older imports/tests.
derive_run_id_from_source = derive_run_path_from_source


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
