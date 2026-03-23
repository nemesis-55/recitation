from __future__ import annotations

import json
import re

from app.config import settings
from app.models.schemas import ScriptLine

_DEFAULT_CHARACTER_PROFILES: dict[str, dict[str, float | str]] = {
    # speed: use gender-unified base (see gender_base_tts_speed); per-slot differences only for timbre direction.
    "male_1": {"stability": 0.34, "similarity_boost": 0.8, "style": 0.52},
    "male_2": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.42},
    "male_3": {"stability": 0.32, "similarity_boost": 0.78, "style": 0.56},
    "male_4": {"stability": 0.45, "similarity_boost": 0.82, "style": 0.36},
    "male_5": {"stability": 0.38, "similarity_boost": 0.79, "style": 0.48},
    "male_6": {"stability": 0.36, "similarity_boost": 0.8, "style": 0.44},
    "male_7": {"stability": 0.42, "similarity_boost": 0.82, "style": 0.4},
    "female_1": {"stability": 0.43, "similarity_boost": 0.82, "style": 0.44},
    "female_2": {"stability": 0.37, "similarity_boost": 0.8, "style": 0.54},
    "female_3": {"stability": 0.48, "similarity_boost": 0.84, "style": 0.38},
    "narrator": {"stability": 0.52, "similarity_boost": 0.84, "style": 0.32},
    "unknown_1": {"stability": 0.42, "similarity_boost": 0.78, "style": 0.4},
}


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


def _character_profiles() -> dict[str, dict[str, float | str]]:
    raw = settings.elevenlabs_character_profiles_json
    if not raw or not str(raw).strip():
        return _DEFAULT_CHARACTER_PROFILES
    try:
        data = json.loads(raw)
    except Exception:
        return _DEFAULT_CHARACTER_PROFILES
    if not isinstance(data, dict):
        return _DEFAULT_CHARACTER_PROFILES
    out = dict(_DEFAULT_CHARACTER_PROFILES)
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        k = str(key).strip().lower()
        base = dict(_DEFAULT_CHARACTER_PROFILES.get(k, {}))
        for field in ("stability", "similarity_boost", "style", "speed"):
            if field in value:
                try:
                    base[field] = float(value[field])
                except Exception:
                    pass
        out[k] = base
    return out


def _infer_gender_from_speaker(speaker: str) -> str:
    sp = (speaker or "").strip().lower()
    if sp.startswith("male_") or sp == "male":
        return "male"
    if sp.startswith("female_") or sp == "female":
        return "female"
    return "unknown"


def gender_base_tts_speed(speaker: str | None) -> float:
    """Shared tempo per gender so male_* / female_* lines don't drift by character slot."""
    sp = (speaker or "").strip().lower()
    if sp == "narrator":
        return max(0.7, min(1.2, float(getattr(settings, "elevenlabs_tts_speed_narrator", 0.96))))
    g = _infer_gender_from_speaker(sp)
    if g == "male":
        return max(0.7, min(1.2, float(getattr(settings, "elevenlabs_tts_speed_male", 0.98))))
    if g == "female":
        return max(0.7, min(1.2, float(getattr(settings, "elevenlabs_tts_speed_female", 0.98))))
    return max(0.7, min(1.2, float(getattr(settings, "elevenlabs_tts_speed_unknown", 0.97))))


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


def get_character_profile(line: ScriptLine, line_index: int) -> dict[str, float]:
    speaker = (line.speaker or "").strip().lower()
    profiles = _character_profiles()
    key = speaker if speaker in profiles else ""
    if not key:
        key = "narrator" if speaker == "narrator" else "unknown_1"
    profile = profiles.get(key, _DEFAULT_CHARACTER_PROFILES["unknown_1"])
    # Tiny deterministic variation by line index to avoid robotic flatness.
    wiggle = ((line_index % 5) - 2) * 0.01
    base_speed = gender_base_tts_speed(speaker)
    if "speed" in profile:
        try:
            base_speed = max(0.85, min(1.15, float(profile["speed"])))
        except Exception:
            pass
    return {
        "stability": max(0.2, min(0.8, float(profile.get("stability", 0.42)) + wiggle)),
        "similarity_boost": max(0.55, min(0.9, float(profile.get("similarity_boost", 0.78)))),
        "style": max(0.0, min(0.9, float(profile.get("style", 0.3)))),
        "speed": base_speed,
    }


def resolved_characters(lines: list[ScriptLine]) -> dict[str, str]:
    """Speaker key -> ElevenLabs voice id (last line for that speaker wins)."""
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        sp = (line.speaker or "unknown_1").lower()
        vid = line.voice or get_voice(line, idx)
        out[sp] = vid
    return out
