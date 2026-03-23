from __future__ import annotations

import re


def _normalize_sfx_token(token: str) -> str:
    t = (token or "").strip().lower()
    if not t:
        return ""
    # Strip non-word boundaries conservatively.
    t = re.sub(r"^[^a-z0-9']+|[^a-z0-9']+$", "", t)
    if not t:
        return ""
    # Collapse long repeated character runs (e.g., woooosh -> woosh, shhhh -> shh).
    t = re.sub(r"([a-z])\1{2,}", r"\1\1", t)
    # Common OCR/onomatopoeia variants -> canonical forms.
    variant_map = {
        "fwoosh": "whoosh",
        "fwhoosh": "whoosh",
        "woosh": "whoosh",
        "whosh": "whoosh",
        "wosh": "whoosh",
        "shh": "shhh",
        "sss": "shhh",
        "aah": "ahh",
        "ahhh": "ahh",
        "hm": "hmm",
        "huhh": "huh",
        "hahh": "hah",
        "clompf": "clomp",
        "thumpf": "thump",
    }
    return variant_map.get(t, t)


_KEYWORDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "impact": (
        "hit",
        "hits",
        "punch",
        "punches",
        "slam",
        "slams",
        "smash",
        "smashes",
        "strike",
        "strikes",
        "attack",
        "attacks",
        "clash",
        "clang",
        "bang",
        "bam",
        "pow",
        "whack",
        "thwack",
        "crack",
        "blast",
        "boom",
        "explosion",
        "explode",
        "shatter",
        "slash",
        "stab",
    ),
    "thump": (
        "fall",
        "fell",
        "drop",
        "dropped",
        "crash",
        "land",
        "landed",
        "thud",
        "thump",
        "thumpf",
        "clomp",
        "clop",
        "stomp",
        "stomped",
        "bump",
        "bonk",
        "knock",
    ),
    "movement": (
        "run",
        "running",
        "rush",
        "rushing",
        "dash",
        "dashing",
        "footsteps",
        "footstep",
        "move",
        "moving",
        "movement",
        "whoosh",
        "swoosh",
        "swish",
        "woosh",
        "fwoosh",
        "waft",
        "rustle",
        "shuffle",
        "scuttle",
        "slide",
        "glide",
        "turn",
        "twist",
        "whirl",
        "zip",
    ),
    "cough": (
        "cough",
        "coughing",
        "hack",
        "ahem",
        "khh",
        "khm",
        "hemhem",
    ),
    "light_breath": (
        "gasp",
        "pant",
        "breath",
        "breathe",
        "breathing",
        "wheeze",
        "huff",
        "huh",
        "ahh",
        "ah",
        "sss",
        "shh",
        "shhh",
        "sigh",
        "sniff",
    ),
    "heavy_breath": (
        "gasp",
        "pant",
        "breath",
        "breathe",
        "breathing",
        "huff",
        "puff",
        "wheeze",
        "heavy",
        "exhale",
        "inhale",
        "hah",
        "haah",
        "hng",
        "ngh",
    ),
}

_FILE_BY_TYPE: dict[str, str] = {
    "impact": "impact.mp3",
    "thump": "thump.mp3",
    "movement": "footsteps.mp3",
    "cough": "cough.mp3",
    "light_breath": "light_breath.mp3",
    "heavy_breath": "heavy_breath.mp3",
    # Common aliases to keep alignment resilient to upstream event labels.
    "metal": "impact.mp3",
    "slash": "impact.mp3",
    "punch": "impact.mp3",
    "fall": "thump.mp3",
    "step": "footsteps.mp3",
    "footstep": "footsteps.mp3",
    "footsteps": "footsteps.mp3",
    "whoosh": "footsteps.mp3",
    "wind": "footsteps.mp3",
    "breath": "light_breath.mp3",
    "gasp": "light_breath.mp3",
    "wheeze": "heavy_breath.mp3",
    "huff": "heavy_breath.mp3",
}


def align_sfx(text: str, audio_duration: float, sfx_type: str) -> dict[str, float | str]:
    words = [_normalize_sfx_token(w) for w in re.findall(r"[A-Za-z0-9']+", (text or "").lower())]
    words = [w for w in words if w]
    duration = max(0.05, float(audio_duration or 0.0))
    if not words:
        return {"sfx": _FILE_BY_TYPE.get(sfx_type, "sfx.mp3"), "timestamp": round(min(0.15, duration * 0.2), 3)}

    keywords = _KEYWORDS_BY_TYPE.get((sfx_type or "").lower(), ())
    idx = -1
    if keywords:
        for i, w in enumerate(words):
            if w in keywords:
                idx = i
                break
    if idx < 0:
        idx = max(0, len(words) // 2)
    timestamp = (float(idx) / max(1.0, float(len(words)))) * duration
    return {
        "sfx": _FILE_BY_TYPE.get((sfx_type or "").lower(), "sfx.mp3"),
        "timestamp": round(max(0.0, min(duration - 0.05, timestamp)), 3),
    }
