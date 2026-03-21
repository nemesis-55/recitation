from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import settings


def _cache_root() -> Path:
    root = settings.output_root / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_cache_json(namespace: str, key: str) -> Any | None:
    if not settings.enable_cache:
        return None
    path = _cache_root() / namespace / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache_json(namespace: str, key: str, payload: Any) -> None:
    if not settings.enable_cache:
        return
    path = _cache_root() / namespace / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def read_cache_bytes(namespace: str, key: str) -> bytes | None:
    if not settings.enable_cache:
        return None
    path = _cache_root() / namespace / f"{key}.bin"
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def write_cache_bytes(namespace: str, key: str, payload: bytes) -> None:
    if not settings.enable_cache:
        return
    path = _cache_root() / namespace / f"{key}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
