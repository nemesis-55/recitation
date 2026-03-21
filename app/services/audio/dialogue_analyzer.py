from __future__ import annotations

from app.models.schemas import ScriptLine


def estimate_emotion_intensity(text: str, emotion: str) -> float:
    base = {"angry": 0.75, "sad": 0.55, "fear": 0.7, "happy": 0.65, "neutral": 0.4}.get(emotion, 0.5)
    bonus = 0.0
    if "!" in text:
        bonus += 0.08
    if "..." in text:
        bonus += 0.06
    if text.isupper() and len(text) >= 6:
        bonus += 0.08
    return max(0.0, min(1.0, base + bonus))


def analyze_dialogue(script: list[ScriptLine]) -> list[ScriptLine]:
    for line in script:
        line.emotion_intensity = estimate_emotion_intensity(line.narration or "", line.emotion or "neutral")
    return script
