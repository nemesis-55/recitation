from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


def catalog_path() -> Path:
    base = settings.output_root / "meta"
    base.mkdir(parents=True, exist_ok=True)
    return base / settings.webtoon_catalog_file


def empty_catalog() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "source": "webtoon_crawl",
        "genres": [],
        "stats": {
            "genre_count": 0,
            "title_count": 0,
            "episode_count": 0,
        },
    }


def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    if not path.exists():
        return empty_catalog()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return empty_catalog()


def save_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else empty_catalog()
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    genres = normalized.get("genres")
    if not isinstance(genres, list):
        genres = []
    title_count = 0
    episode_count = 0
    for genre in genres:
        titles = genre.get("titles", []) if isinstance(genre, dict) else []
        title_count += len(titles)
        for title in titles:
            eps = title.get("episodes", []) if isinstance(title, dict) else []
            episode_count += len(eps)
    normalized["stats"] = {
        "genre_count": len(genres),
        "title_count": title_count,
        "episode_count": episode_count,
    }
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=True, indent=2), encoding="utf-8")
    return normalized


def _parse_updated_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # Accept standard ISO and trailing Z format.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def catalog_is_stale(payload: dict[str, Any], max_age_hours: int = 24) -> bool:
    updated_at = _parse_updated_at(payload.get("updated_at") if isinstance(payload, dict) else None)
    if updated_at is None:
        return True
    safe_hours = max(1, int(max_age_hours))
    age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
    return age_seconds >= safe_hours * 3600


def search_titles(query: str | None = None, genre: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    payload = load_catalog()
    q = (query or "").strip().lower()
    wanted_genre = (genre or "").strip().lower()
    items: list[dict[str, Any]] = []
    for g in payload.get("genres", []):
        if not isinstance(g, dict):
            continue
        gslug = str(g.get("genre", "")).strip().lower()
        if wanted_genre and gslug != wanted_genre:
            continue
        for t in g.get("titles", []):
            if not isinstance(t, dict):
                continue
            title_name = str(t.get("title_name", "")).strip()
            title_slug = str(t.get("title_slug", "")).strip()
            if q and q not in title_name.lower() and q not in title_slug.lower():
                continue
            items.append(
                {
                    "genre": gslug,
                    "title_slug": title_slug,
                    "title_name": title_name,
                    "title_no": t.get("title_no"),
                    "episode_count": len(t.get("episodes", [])),
                }
            )
    items.sort(key=lambda x: (x["genre"], x["title_name"]))
    safe_offset = max(0, int(offset))
    safe_limit = max(0, int(limit))
    return {
        "items": items[safe_offset : safe_offset + safe_limit],
        "total": len(items),
        "updated_at": payload.get("updated_at"),
        "stats": payload.get("stats", {}),
    }


def _configured_genre_slugs() -> list[str]:
    """Genre keys from WEBTOON_CATALOG_GENRE_URLS_JSON (object form), for UI dropdown before first crawl."""
    raw = settings.webtoon_catalog_genre_urls_json
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if isinstance(parsed, dict):
        return sorted({str(k).strip().lower() for k in parsed.keys() if str(k).strip()})
    return []


def list_genres() -> list[str]:
    """Distinct genre slugs: configured in .env first, then merged with catalog on disk."""
    seen: set[str] = set()
    ordered: list[str] = []
    for g in _configured_genre_slugs():
        if g not in seen:
            seen.add(g)
            ordered.append(g)
    payload = load_catalog()
    for block in payload.get("genres", []):
        if not isinstance(block, dict):
            continue
        slug = str(block.get("genre", "")).strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    ordered.sort()
    return ordered


def list_episodes(title_slug: str) -> list[dict[str, Any]]:
    wanted = title_slug.strip().lower()
    payload = load_catalog()
    for g in payload.get("genres", []):
        if not isinstance(g, dict):
            continue
        for t in g.get("titles", []):
            if not isinstance(t, dict):
                continue
            if str(t.get("title_slug", "")).strip().lower() != wanted:
                continue
            episodes = [e for e in t.get("episodes", []) if isinstance(e, dict)]
            episodes.sort(key=lambda e: int(e.get("episode_no") or 0))
            return episodes
    return []

