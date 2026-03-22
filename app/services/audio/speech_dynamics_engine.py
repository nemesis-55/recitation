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

    out: list[str] = []
    for i, raw in enumerate(words):
        w = _stretch_word(raw, emo, t)
        out.append(w)
        if i >= len(words) - 1:
            continue
        d = _word_delay(w, emo, t)
        # Broken delivery for fear and gentle trailing for sadness.
        if emo == "fear" and t >= 0.45 and (i % 3 == 1):
            d = max(d, 0.28 + (0.12 * t))
        if emo == "sad" and (i % 4 == 2):
            d = max(d, 0.24 + (0.1 * t))
        if emo == "angry":
            d = min(d, 0.16)
        out.append(_pause_token(d))

    rendered = "".join(out).strip()
    if emo == "angry":
        rendered = re.sub(r"[.]{2,}", "!", rendered)
        if t >= 0.65:
            rendered = rendered.upper()
        if rendered and rendered[-1] not in "!?":
            rendered += "!"
    elif emo == "fear":
        rendered = re.sub(r"\s{2,}", " ", rendered)
        if t >= 0.6 and not rendered.endswith("..."):
            rendered += "..."
    elif emo == "sad":
        if not rendered.endswith("..."):
            rendered += "..."
    return rendered
