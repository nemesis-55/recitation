from __future__ import annotations

import re
from pathlib import Path

from app.models.schemas import ScriptLine


def _sfx_map() -> dict[str, str]:
    return {
        "fear": "breath_light.mp3",
        "angry": "impact_thump_soft.mp3",
        "sad": "soft_exhale.mp3",
        "neutral": "room_tone_soft.mp3",
        "happy": "room_tone_soft.mp3",
    }


def pick_sfx(line: ScriptLine, sfx_root: Path) -> list[Path]:
    emotion = (line.emotion or "neutral").lower()
    narration = (line.narration or "").lower()
    files: list[Path] = []
    mapped = _sfx_map().get(emotion)
    if mapped:
        p = sfx_root / mapped
        if p.exists():
            files.append(p)
    # Keep exertion sounds subtle and non-explicit.
    if re.search(r"\b(hu+|ha+|ah+|uh+)\b", narration):
        p = sfx_root / "breath_heavy.mp3"
        if p.exists():
            files.append(p)
    return files[:2]
