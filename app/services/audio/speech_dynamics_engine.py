from __future__ import annotations

import re


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _pause_token(seconds: float) -> str:
    # ElevenLabs responds well to comma/ellipsis punctuation as micro-pauses.
    if seconds >= 0.32:
        return "... "
    if seconds >= 0.2:
        return ", "
    return " "


def _word_delay(word: str, emotion: str, intensity: float) -> float:
    n = len(re.sub(r"[^A-Za-z0-9]", "", word))
    if n <= 3:
        base = 0.08
    elif n <= 7:
        base = 0.14
    else:
        base = 0.22
    emo = (emotion or "neutral").lower()
    t = _clamp01(intensity)
    if emo == "angry":
        base *= max(0.55, 0.9 - (0.3 * t))
    elif emo == "fear":
        base *= 1.15 + (0.25 * t)
    elif emo == "sad":
        base *= 1.25 + (0.35 * t)
    return min(0.4, max(0.08, base))


def _stretch_word(word: str, emotion: str, intensity: float) -> str:
    emo = (emotion or "neutral").lower()
    t = _clamp01(intensity)
    token = re.sub(r"[^A-Za-z]", "", word)
    if len(token) < 4:
        return word
    if emo == "sad" and t >= 0.55 and len(token) >= 6:
        return re.sub(r"([aeiouAEIOU])", r"\1-", word, count=1)
    if emo == "fear" and t >= 0.65 and len(token) >= 5:
        return f"{word[:1]}-{word[1:]}"
    return word


def apply_speech_dynamics(text: str, emotion: str, intensity: float) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    emo = (emotion or "neutral").lower()
    t = _clamp01(intensity)
    words = cleaned.split(" ")

    out: list[str] = [_stretch_word(raw, emo, t) for raw in words]
    rendered = " ".join(out).strip()
    if emo == "angry":
        rendered = re.sub(r"[.]{2,}", ".", rendered)
        if t >= 0.48:
            rendered = rendered.upper()
        if rendered and rendered[-1] not in "!?":
            rendered += "!"
    elif emo == "surprised":
        if rendered and rendered[-1] not in "!?":
            rendered += "!"
    elif emo == "curious":
        if rendered and rendered[-1] not in ".!?":
            rendered += "?"
    elif emo == "confused":
        if rendered and rendered[-1] not in ".!?":
            rendered += "?"
    elif emo in {"determined", "serious"}:
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    elif emo == "hopeful":
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    elif emo in {"resigned", "weak", "pain"}:
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    elif emo in {"concerned", "worried"}:
        if rendered and rendered[-1] not in ".!?":
            rendered += "?"
    elif emo in {"urgent", "desperate"}:
        if rendered and rendered[-1] not in "!?":
            rendered += "!"
    elif emo in {"frustrated", "teasing"} and t >= 0.5:
        if rendered and rendered[-1] not in ".!?":
            rendered += "!"
    elif emo in {"nostalgic", "regretful", "reassuring"}:
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    elif emo == "apologetic":
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    elif emo == "fear":
        rendered = re.sub(r"\s{2,}", " ", rendered).strip()
    elif emo == "sad":
        if rendered and rendered[-1] not in ".!?":
            rendered += "."
    return rendered
