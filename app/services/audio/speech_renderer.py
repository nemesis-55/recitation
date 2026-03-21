from __future__ import annotations

import re


def render_speech(text: str, emotion: str, intensity: float) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    # Keep exertion vocals instead of skipping them.
    if re.match(r"^h+u+$", lowered) or re.match(r"^h+a+$", lowered):
        cleaned = f"{cleaned}..."
    if emotion == "fear" and intensity >= 0.55:
        cleaned = cleaned.replace(" ", "... ")
        if not cleaned.startswith("..."):
            cleaned = "... " + cleaned
    elif emotion == "sad" and intensity >= 0.5:
        cleaned = f"... {cleaned}..."
    elif emotion == "angry" and intensity >= 0.72 and len(cleaned) <= 90:
        cleaned = cleaned.upper()
    elif emotion == "happy" and intensity >= 0.6 and cleaned[-1] not in "!":
        cleaned = f"{cleaned}!"
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned
