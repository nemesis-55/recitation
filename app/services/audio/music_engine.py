"""
Local / default-BGM beds only (no ElevenLabs music API).
Pick a loopable file from AUDIO_MUSIC_LOCAL_MAP_JSON or BGM_DEFAULT_PATH.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.config import settings
from app.models.schemas import ScriptLine
from app.services.audio.pause_engine import pause_seconds


def _load_local_emotion_paths() -> dict[str, str]:
    raw = settings.audio_music_local_map_json
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception:
        return {}


def _dominant_emotion(lines: list[ScriptLine]) -> str:
    emotions = [(line.emotion or "neutral").lower() for line in lines if (line.narration or "").strip()]
    if not emotions:
        return "neutral"
    counts = Counter(emotions)
    return counts.most_common(1)[0][0]


_EMOTION_LABELS: dict[str, str] = {
    "sad": "Slow emotional solo piano, cinematic underscore, very sparse, loopable",
    "fear": "Dark tension drones, subtle strings, loopable",
    "angry": "Low pulse, action tension, subtle percussion, loopable instrumental",
    "happy": "Light upbeat ambient bed, soft pads, loopable instrumental",
    "neutral": "Soft ambient underscore, minimal, loopable instrumental",
}


def estimate_script_narration_duration_sec(lines: list[ScriptLine]) -> float:
    total = 0.0
    for line in lines:
        text = (line.narration or "").strip()
        if not text:
            continue
        emo = (line.emotion or "neutral").lower()
        inten = float(line.emotion_intensity if line.emotion_intensity is not None else 0.5)
        pause = pause_seconds(emo, inten)
        total += max(1.2, len(text) * 0.048)
        total += pause
    return max(5.0, total)


def resolve_music_bed(lines: list[ScriptLine], audio_dir: Path) -> tuple[Path | None, str, str]:
    """
    Returns (path_or_none, source, reason) where source is local_map, bgm_default, or none.
    """
    _ = audio_dir  # reserved for future per-run copied beds
    if not settings.audio_bed_in_narration:
        return None, "none", "audio_bed_in_narration_disabled"

    emotion = _dominant_emotion(lines)
    local_map = _load_local_emotion_paths()
    if emotion in local_map:
        candidate = Path(local_map[emotion])
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return candidate.resolve(), "local_map", ""

    if settings.audio_use_bgm_default_as_bed and settings.bgm_default_path:
        bgm = Path(settings.bgm_default_path)
        if bgm.exists():
            return bgm.resolve(), "bgm_default", ""

    return None, "none", "no_local_music_or_bgm_default"


def music_prompt_for_emotion(emotion: str) -> str:
    """Documentation / tests only — no network call."""
    return _EMOTION_LABELS.get((emotion or "neutral").lower(), _EMOTION_LABELS["neutral"])
