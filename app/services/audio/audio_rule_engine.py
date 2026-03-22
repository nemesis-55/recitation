from __future__ import annotations

from dataclasses import dataclass


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
    "angry": EmotionRule(0.25, 0.35, 1.10, "uppercase_exclaim", ("impact",), 2, "intense", 0.15, 0.35),
    "fear": EmotionRule(0.40, 0.55, 0.90, "broken_pause", ("light_breath", "heavy_breath"), 2, "tension", 0.50, 1.00),
    "sad": EmotionRule(0.50, 0.65, 0.85, "trailing_pause", (), 0, "piano", 0.60, 1.00),
    "happy": EmotionRule(0.32, 0.45, 1.03, "none", (), 0, "uplift", 0.22, 0.40),
    "neutral": EmotionRule(0.45, 0.55, 1.00, "none", (), 0, "ambient", 0.30, 0.40),
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * _clamp01(t)


def resolve_audio_plan(text: str, emotion: str, intensity: float, scene_type: str) -> dict:
    _ = text
    emo = (emotion or "neutral").lower()
    rule = EMOTION_RULES.get(emo, EMOTION_RULES["neutral"])
    t = _clamp01(float(intensity))

    stability = _lerp(rule.voice_stability_min, rule.voice_stability_max, t)
    speed = rule.voice_speed
    sfx_types = list(rule.sfx_types)
    sfx_max = int(rule.sfx_max)
    music_type = rule.music_type
    pause = _lerp(rule.pause_min, rule.pause_max, t)

    scene = (scene_type or "neutral").lower()
    if scene == "fight":
        speed = min(1.18, speed + 0.04)
        pause = max(0.10, pause - 0.08)
        if "impact" not in sfx_types:
            sfx_types = ["impact", *sfx_types]
        sfx_max = max(sfx_max, 1)
        music_type = "intense"
    elif scene == "emotional":
        pause = min(1.20, pause + 0.10)
        if emo in {"sad", "fear"}:
            music_type = "piano" if emo == "sad" else "tension"

    return {
        "voice_settings": {
            "stability": round(stability, 3),
            "similarity_boost": 0.8,
            "style": round(_lerp(0.2, 0.8, t), 3),
            "speed": round(speed, 3),
        },
        "speech_mode": rule.speech_mode,
        "sfx_plan": sfx_types[:sfx_max],
        "music_type": music_type,
        "pause": round(pause, 3),
    }

