from __future__ import annotations

import re

from app.config import settings
from app.services.audio.speech_dynamics_engine import apply_speech_dynamics
from app.services.audio.tts_text_normalize import normalize_tts_narration


_SFX_WORDS = {
    "swoosh",
    "swish",
    "slash",
    "slashing",
    "whoosh",
    "bam",
    "bang",
    "thud",
    "pow",
    "smash",
    "clang",
}


def _looks_like_sfx_noise(text: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    if not tokens:
        return False
    sfx_hits = sum(1 for t in tokens if t in _SFX_WORDS)
    # If most tokens are effects-only words, prefer silence for cleaner narration.
    return len(tokens) <= 4 and sfx_hits >= max(1, len(tokens) - 1)


def _apply_speech_mode(cleaned: str, mode: str) -> str:
    m = (mode or "none").strip().lower()
    if m == "uppercase_exclaim":
        out = cleaned.upper()
        if not out.endswith("!"):
            out += "!"
        return out
    if m == "broken_pause":
        parts = re.split(r"([,;:.!?])", cleaned)
        rebuilt = "".join(parts).strip()
        return rebuilt.replace(",", ", ").replace("  ", " ")
    if m == "trailing_pause":
        if cleaned.endswith("."):
            return cleaned
        return f"{cleaned}."
    return cleaned


def _render_speech_impl(
    text: str,
    emotion: str,
    intensity: float,
    speech_mode: str,
    *,
    apply_tts_pronunciation_fixes: bool,
    blank_sfx_only_lines: bool,
) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if apply_tts_pronunciation_fixes and getattr(settings, "tts_narration_normalize_enabled", True):
        cleaned = normalize_tts_narration(cleaned)
    if blank_sfx_only_lines and _looks_like_sfx_noise(cleaned):
        return ""
    cleaned = cleaned.replace("/", ", ")
    cleaned = re.sub(r"[~*_`]+", "", cleaned)
    cleaned = _apply_speech_mode(cleaned, speech_mode)
    cleaned = apply_speech_dynamics(cleaned, emotion, intensity)
    lowered = cleaned.lower()
    # Keep exertion vocals instead of skipping them.
    if re.match(r"^h+u+$", lowered) or re.match(r"^h+a+$", lowered):
        cleaned = f"{cleaned}..."
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def render_speech_for_display(text: str, emotion: str, intensity: float, speech_mode: str = "none") -> str:
    """
    Text for subtitles / ``performance_text``: same delivery rules as TTS but **no**
    pronunciation-only rewrites (OCR wording preserved, including long letter runs).
    SFX-only lines are **not** blanked so subtitles can still show the OCR line.
    """
    return _render_speech_impl(
        text,
        emotion,
        intensity,
        speech_mode,
        apply_tts_pronunciation_fixes=False,
        blank_sfx_only_lines=False,
    )


def render_speech(text: str, emotion: str, intensity: float, speech_mode: str = "none") -> str:
    """
    Text sent to TTS: optional ``normalize_tts_narration`` (stretched letters → pronounceable),
    and SFX-only lines become silent.
    """
    return _render_speech_impl(
        text,
        emotion,
        intensity,
        speech_mode,
        apply_tts_pronunciation_fixes=True,
        blank_sfx_only_lines=True,
    )
