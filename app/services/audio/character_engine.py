from __future__ import annotations

from app.config import settings
from app.models.schemas import ScriptLine


def get_voice(line: ScriptLine, line_index: int) -> str:
    speaker = (line.speaker or "unknown_1").lower()
    gender = (line.gender or "unknown").lower()
    if speaker == "narrator":
        return settings.elevenlabs_voice_narrator
    if gender == "male":
        return settings.elevenlabs_voice_male
    if gender == "female":
        return settings.elevenlabs_voice_female
    return settings.elevenlabs_voice_male if line_index % 2 == 0 else settings.elevenlabs_voice_female
