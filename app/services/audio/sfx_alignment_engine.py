from __future__ import annotations

import re


_KEYWORDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "impact": ("hit", "punch", "slam", "smash", "strike", "attack"),
    "thump": ("fall", "fell", "drop", "crash", "land"),
    "movement": ("run", "rush", "dash", "footsteps", "move", "movement"),
    "light_breath": ("gasp", "pant", "breath"),
    "heavy_breath": ("gasp", "pant", "breath"),
}

_FILE_BY_TYPE: dict[str, str] = {
    "impact": "impact.mp3",
    "thump": "thump.mp3",
    "movement": "footsteps.mp3",
    "light_breath": "light_breath.mp3",
    "heavy_breath": "heavy_breath.mp3",
}


def align_sfx(text: str, audio_duration: float, sfx_type: str) -> dict[str, float | str]:
    words = re.findall(r"[A-Za-z0-9']+", (text or "").lower())
    duration = max(0.05, float(audio_duration or 0.0))
    if not words:
        return {"sfx": _FILE_BY_TYPE.get(sfx_type, "sfx.mp3"), "timestamp": round(min(0.15, duration * 0.2), 3)}

    keywords = _KEYWORDS_BY_TYPE.get((sfx_type or "").lower(), ())
    idx = -1
    if keywords:
        for i, w in enumerate(words):
            if w in keywords:
                idx = i
                break
    if idx < 0:
        idx = max(0, len(words) // 2)
    timestamp = (float(idx) / max(1.0, float(len(words)))) * duration
    return {
        "sfx": _FILE_BY_TYPE.get((sfx_type or "").lower(), "sfx.mp3"),
        "timestamp": round(max(0.0, min(duration - 0.05, timestamp)), 3),
    }
