from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.services.audio.character_engine import gender_base_tts_speed


@dataclass(frozen=True)
class EmotionRule:
    voice_stability_min: float
    voice_stability_max: float
    voice_speed: float
    speech_mode: str
    sfx_types: tuple[str, ...]
    sfx_max: int
    music_type: str
    pause_min: float
    pause_max: float


EMOTION_RULES: dict[str, EmotionRule] = {
    "angry": EmotionRule(0.25, 0.35, 1.08, "uppercase_exclaim", ("impact",), 1, "intense", 0.10, 0.22),
    "fear": EmotionRule(0.40, 0.55, 0.94, "broken_pause", ("movement",), 1, "tension", 0.18, 0.30),
    "sad": EmotionRule(0.50, 0.65, 0.90, "trailing_pause", (), 0, "piano", 0.20, 0.34),
    "happy": EmotionRule(0.32, 0.45, 1.02, "none", (), 0, "uplift", 0.12, 0.22),
    "neutral": EmotionRule(0.45, 0.55, 1.00, "none", (), 0, "ambient", 0.12, 0.20),
    "surprised": EmotionRule(0.30, 0.42, 1.07, "uppercase_exclaim", ("impact",), 1, "tension", 0.10, 0.18),
    "curious": EmotionRule(0.42, 0.54, 0.98, "none", (), 0, "ambient", 0.14, 0.24),
    "confused": EmotionRule(0.44, 0.58, 0.95, "broken_pause", ("movement",), 1, "tension", 0.16, 0.28),
    "determined": EmotionRule(0.34, 0.46, 1.03, "none", ("impact",), 1, "uplift", 0.11, 0.19),
    "hopeful": EmotionRule(0.37, 0.5, 1.0, "none", (), 0, "uplift", 0.12, 0.22),
    "resigned": EmotionRule(0.52, 0.64, 0.92, "trailing_pause", (), 0, "ambient", 0.2, 0.34),
    "pain": EmotionRule(0.3, 0.42, 0.95, "broken_pause", (), 0, "tension", 0.17, 0.3),
    "concerned": EmotionRule(0.45, 0.58, 0.98, "none", (), 0, "ambient", 0.15, 0.26),
    "worried": EmotionRule(0.42, 0.56, 0.95, "broken_pause", (), 0, "tension", 0.18, 0.3),
    "weak": EmotionRule(0.56, 0.68, 0.88, "trailing_pause", (), 0, "piano", 0.2, 0.34),
    "urgent": EmotionRule(0.26, 0.36, 1.1, "uppercase_exclaim", ("impact",), 1, "intense", 0.09, 0.2),
    "nostalgic": EmotionRule(0.48, 0.6, 0.93, "trailing_pause", (), 0, "piano", 0.18, 0.32),
    "reassuring": EmotionRule(0.4, 0.52, 0.97, "none", (), 0, "uplift", 0.12, 0.22),
    "regretful": EmotionRule(0.52, 0.64, 0.9, "trailing_pause", (), 0, "piano", 0.2, 0.34),
    "apologetic": EmotionRule(0.48, 0.6, 0.94, "broken_pause", (), 0, "ambient", 0.16, 0.28),
    "serious": EmotionRule(0.4, 0.52, 0.97, "none", (), 0, "ambient", 0.13, 0.24),
    "desperate": EmotionRule(0.3, 0.42, 1.0, "broken_pause", ("movement",), 1, "tension", 0.18, 0.32),
    "defensive": EmotionRule(0.42, 0.55, 0.97, "none", (), 0, "tension", 0.14, 0.26),
    "frustrated": EmotionRule(0.32, 0.46, 1.05, "none", ("impact",), 1, "tension", 0.12, 0.24),
    "teasing": EmotionRule(0.34, 0.46, 1.04, "none", (), 0, "uplift", 0.09, 0.18),
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * _clamp01(t)


def resolve_audio_plan(
    text: str,
    emotion: str,
    intensity: float,
    scene_type: str,
    *,
    speaker: str | None = None,
) -> dict:
    _ = text
    emo = (emotion or "neutral").lower()
    rule = EMOTION_RULES.get(emo, EMOTION_RULES["neutral"])
    t = _clamp01(float(intensity))

    stability = _lerp(rule.voice_stability_min, rule.voice_stability_max, t)
    emotion_speed = float(rule.voice_speed)
    sfx_types = list(rule.sfx_types)
    sfx_max = int(rule.sfx_max)
    music_type = rule.music_type
    pause = _lerp(rule.pause_min, rule.pause_max, t)

    scene = (scene_type or "neutral").lower()
    if scene == "fight":
        emotion_speed = min(1.18, emotion_speed + 0.04)
        pause = max(0.08, pause - 0.05)
        if "impact" not in sfx_types:
            sfx_types = ["impact", *sfx_types]
        sfx_max = max(sfx_max, 1)
        music_type = "intense"
    elif scene == "emotional":
        pause = min(0.45, pause + 0.04)
        if emo in {
            "sad",
            "fear",
            "confused",
            "resigned",
            "worried",
            "weak",
            "pain",
            "nostalgic",
            "regretful",
            "concerned",
            "serious",
            "desperate",
            "defensive",
            "frustrated",
        }:
            music_type = "piano" if emo in {"sad", "weak", "resigned", "nostalgic", "regretful"} else "tension"
        elif emo == "reassuring":
            music_type = "uplift"

    mix = float(getattr(settings, "elevenlabs_tts_emotion_speed_mix", 0.38))
    base_sp = gender_base_tts_speed(speaker)
    speed = base_sp + (emotion_speed - 1.0) * mix
    speed = max(0.84, min(1.14, float(speed)))

    return {
        "voice_settings": {
            "stability": round(stability, 3),
            "similarity_boost": 0.8,
            "style": round(_lerp(0.25, 0.88, t), 3),
            "speed": round(speed, 3),
        },
        "speech_mode": rule.speech_mode,
        "sfx_plan": sfx_types[:sfx_max],
        "music_type": music_type,
        "pause": round(pause, 3),
    }

