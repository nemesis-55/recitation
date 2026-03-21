from __future__ import annotations

import json

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


def get_voice(line: ScriptLine, line_index: int) -> str:
    speaker = (line.speaker or "unknown_1").lower()
    vm = _voice_map()
    if speaker in vm and vm[speaker]:
        return vm[speaker]
    gender = (line.gender or "unknown").lower()
    if speaker == "narrator":
        return settings.elevenlabs_voice_narrator
    if gender == "male":
        return settings.elevenlabs_voice_male
    if gender == "female":
        return settings.elevenlabs_voice_female
    return settings.elevenlabs_voice_male if line_index % 2 == 0 else settings.elevenlabs_voice_female


def resolved_characters(lines: list[ScriptLine]) -> dict[str, str]:
    """Speaker key -> ElevenLabs voice id (last line for that speaker wins)."""
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        sp = (line.speaker or "unknown_1").lower()
        vid = line.voice or get_voice(line, idx)
        out[sp] = vid
    return out
