from __future__ import annotations

import json
import re

from app.config import settings
from app.models.schemas import ScriptLine


def _voice_map() -> dict[str, str]:
    raw = settings.elevenlabs_voice_map_json
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception:
        return {}


def _infer_gender_from_speaker(speaker: str) -> str:
    sp = (speaker or "").strip().lower()
    if sp.startswith("male_") or sp == "male":
        return "male"
    if sp.startswith("female_") or sp == "female":
        return "female"
    return "unknown"


def _speaker_slot(speaker: str, prefix: str, max_slot: int) -> int | None:
    sp = (speaker or "").strip().lower()
    m = re.match(rf"^{prefix}_(\d+)$", sp)
    if not m:
        return None
    try:
        slot = int(m.group(1))
    except Exception:
        return None
    if slot < 1 or slot > max_slot:
        return None
    return slot


def _male_voice_pool() -> list[str]:
    return [
        settings.elevenlabs_voice_male,
        settings.elevenlabs_voice_male_2,
        settings.elevenlabs_voice_male_3,
        settings.elevenlabs_voice_male_4,
        settings.elevenlabs_voice_male_5,
        settings.elevenlabs_voice_male_6,
        settings.elevenlabs_voice_male_7,
    ]


def _female_voice_pool() -> list[str]:
    return [
        settings.elevenlabs_voice_female,
        settings.elevenlabs_voice_female_2,
        settings.elevenlabs_voice_female_3,
    ]


def get_voice(line: ScriptLine, line_index: int) -> str:
    _ = line_index
    speaker = (line.speaker or "unknown_1").lower()
    vm = _voice_map()
    if speaker in vm and vm[speaker]:
        return vm[speaker]
    if speaker == "narrator":
        return settings.elevenlabs_voice_narrator
    male_slot = _speaker_slot(speaker, "male", 7)
    if male_slot is not None:
        return _male_voice_pool()[male_slot - 1]
    female_slot = _speaker_slot(speaker, "female", 3)
    if female_slot is not None:
        return _female_voice_pool()[female_slot - 1]
    gender = (line.gender or "unknown").lower()
    if gender not in {"male", "female"}:
        gender = _infer_gender_from_speaker(speaker)
    if gender == "male":
        return settings.elevenlabs_voice_male
    if gender == "female":
        return settings.elevenlabs_voice_female
    return settings.elevenlabs_voice_unknown


def resolved_characters(lines: list[ScriptLine]) -> dict[str, str]:
    """Speaker key -> ElevenLabs voice id (last line for that speaker wins)."""
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        sp = (line.speaker or "unknown_1").lower()
        vid = line.voice or get_voice(line, idx)
        out[sp] = vid
    return out
