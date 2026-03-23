"""
TTS-only pronunciation helpers: do **not** rewrite OCR wording (no spelling substitutions).

Invalid / non-pronounceable stretches (e.g. comic onomatopoeia) are normalized so the
voice can read them; subtitles should use the raw line (see ``render_speech_for_display``).
"""

from __future__ import annotations

import re

# Three or more identical Latin letters → two ("wooooooo" → "woo", "yesss" → "yess").
_RE_STRETCHED_LETTERS = re.compile(r"([a-zA-Z])\1{2,}")


def normalize_tts_narration(text: str) -> str:
    """
    - Collapse 3+ repeated Latin letters to **two** (readable stretch, keeps e.g. "woo").
    - Trim runs of ! and ?.

    Does **not** change valid words or OCR spellings (no pinyin respelling).
    """
    if not text or not text.strip():
        return text
    t = _RE_STRETCHED_LETTERS.sub(r"\1\1", text)
    t = re.sub(r"!{2,}", "!", t)
    t = re.sub(r"\?{2,}", "?", t)
    return t
