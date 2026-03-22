from __future__ import annotations

import re

from app.config import settings
from app.services.audio.speech_dynamics_engine import apply_speech_dynamics


_SCENE_BRIDGES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bservant[s]?\b", re.IGNORECASE), "Servants move in the background with quiet urgency."),
    (re.compile(r"\bpalace|court|throne|king|queen\b", re.IGNORECASE), "The court carries a heavy silence."),
    (re.compile(r"\bsword|blade|fight|battle|war\b", re.IGNORECASE), "The threat of violence hangs in the air."),
    (re.compile(r"\bdoor|gate|hall|corridor|stairs\b", re.IGNORECASE), "The scene shifts through the passageway."),
    (re.compile(r"\bnight|dark|shadow|moon\b", re.IGNORECASE), "Shadows gather around the moment."),
]
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


def _simple_pronoun_shift(text: str) -> str:
    # Conservative first->third person shift to keep lines natural.
    out = text
    swaps = [
        (r"\bI am\b", "they are"),
        (r"\bI'm\b", "they are"),
        (r"\bI\b", "they"),
        (r"\bme\b", "them"),
        (r"\bmy\b", "their"),
        (r"\bmine\b", "theirs"),
        (r"\bwe are\b", "they are"),
        (r"\bwe\b", "they"),
        (r"\bour\b", "their"),
        (r"\bours\b", "theirs"),
        (r"\bus\b", "them"),
    ]
    for pat, rep in swaps:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)
    return out


def _to_third_person(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith(("the ", "he ", "she ", "they ", "it ")):
        return text
    if re.search(r"\b(i|me|my|mine|we|our|us)\b", lowered):
        return _simple_pronoun_shift(text)
    # Keep original line if already neutral/objective to avoid robotic wrappers.
    return text


def _scene_bridge(text: str, emotion: str, intensity: float) -> str:
    if not settings.audio_scene_bridge_enabled:
        return ""
    for pattern, line in _SCENE_BRIDGES:
        if pattern.search(text):
            return line
    if intensity < 0.55:
        return ""
    emo = (emotion or "neutral").lower()
    if emo == "fear":
        return "A tense stillness settles over the scene."
    if emo == "sad":
        return "A quiet grief lingers in the air."
    if emo == "angry":
        return "The air tightens with rising anger."
    if emo == "happy":
        return "A hopeful warmth touches the scene."
    return ""


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


def render_speech(text: str, emotion: str, intensity: float, speech_mode: str = "none") -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if _looks_like_sfx_noise(cleaned):
        return ""
    cleaned = cleaned.replace("/", ", ")
    cleaned = re.sub(r"[~*_`]+", "", cleaned)
    cleaned = _apply_speech_mode(cleaned, speech_mode)
    cleaned = apply_speech_dynamics(cleaned, emotion, intensity)
    lowered = cleaned.lower()
    # Keep exertion vocals instead of skipping them.
    if re.match(r"^h+u+$", lowered) or re.match(r"^h+a+$", lowered):
        cleaned = f"{cleaned}..."
    cleaned = _to_third_person(cleaned)
    bridge = _scene_bridge(cleaned, emotion, intensity)
    if bridge:
        cleaned = f"{bridge} {cleaned}"
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned
