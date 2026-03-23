from __future__ import annotations

import re

from app.models.schemas import SrtTimelineLine

_SFX_TOKEN_TO_EVENT: dict[str, str] = {
    "whoosh": "movement",
    "swoosh": "movement",
    "swish": "movement",
    "slash": "movement",
    "rush": "movement",
    "footstep": "movement",
    "footsteps": "movement",
    "slam": "impact",
    "smash": "impact",
    "thud": "thump",
    "clomp": "thump",
    "clop": "thump",
    "stomp": "thump",
    "crash": "impact",
    "bang": "impact",
    "bam": "impact",
    "thwack": "impact",
    "whack": "impact",
    "clang": "impact",
    "clash": "impact",
    "strike": "impact",
    "hit": "impact",
    "cough": "cough",
    "coughing": "cough",
    "step": "movement",
    "crackle": "movement",
}


def _dedup_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return out


def _extract_segment_cues(segment: str) -> list[str]:
    words = re.findall(r"[A-Za-z']+", segment)
    return [_SFX_TOKEN_TO_EVENT[w.lower()] for w in words if w.lower() in _SFX_TOKEN_TO_EVENT]


def _strip_embedded_sfx_tokens(segment: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return "" if token.lower() in _SFX_TOKEN_TO_EVENT else token

    cleaned = re.sub(r"[A-Za-z']+", _repl, segment)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip(" -\t\r\n")


def _is_likely_sfx_segment(segment: str) -> bool:
    words = re.findall(r"[A-Za-z']+", segment)
    if not words:
        return False
    hits = sum(1 for w in words if w.lower() in _SFX_TOKEN_TO_EVENT)
    if hits == 0:
        return False
    all_caps = segment.upper() == segment
    mostly_hits = hits >= max(1, int(len(words) * 0.6))
    return (all_caps and mostly_hits and len(words) <= 8) or (hits == len(words) and len(words) <= 6)


_RE_LIKE_COUNT = re.compile(
    r"^\s*\d+\s+people\s+like\s+this\s+post\.?\s*$",
    re.IGNORECASE,
)
_RE_LIKE_THIS = re.compile(
    r"^\s*\d+\s+(people|person|users?)\s+like\s+(this|it)\.?\s*$",
    re.IGNORECASE,
)
_RE_SHARE_COMMENT = re.compile(
    r"^\s*(share|comment|like)\s*$",
    re.IGNORECASE,
)


def _line_is_hashtag_only(segment: str) -> bool:
    s = segment.strip()
    if not s:
        return True
    tokens = re.findall(r"[^\s]+", s)
    if not tokens:
        return True
    return all(t.startswith("#") and len(t) > 1 for t in tokens)


def _heuristic_clean_social_segment(segment: str) -> str:
    """Drop obvious social UI / engagement lines; trim usernames and stray UI words."""
    raw = segment.strip()
    if not raw:
        return ""
    one_line = " ".join(raw.split())
    if _RE_LIKE_COUNT.match(one_line) or _RE_LIKE_THIS.match(one_line):
        return ""
    if _RE_SHARE_COMMENT.match(one_line):
        return ""
    if _line_is_hashtag_only(one_line):
        return ""
    # Strip leading "username: " patterns (social captions).
    one_line = re.sub(r"^[A-Za-z0-9._-]{2,32}\s*:\s*", "", one_line)
    return one_line.strip()


def heuristic_clean_social_ui_text(text: str) -> str:
    """Apply per-line UI heuristics to multi-line OCR blobs (no API)."""
    if not (text or "").strip():
        return ""
    parts = [p.strip() for p in re.split(r"[\n\r]+", text) if p.strip()]
    kept = [_heuristic_clean_social_segment(p) for p in parts]
    kept = [p for p in kept if p]
    return "\n".join(kept).strip()


def filter_ocr_narration_and_extract_sfx(lines: list[SrtTimelineLine], emit_sfx_cues: bool = True) -> list[SrtTimelineLine]:
    for ln in lines:
        text = (ln.text or "").strip()
        if not text:
            ln.sfx_cues = []
            continue
        parts = [p.strip() for p in re.split(r"[\n\r]+", text) if p.strip()]
        kept: list[str] = []
        cues: list[str] = []
        for part in parts:
            if _is_likely_sfx_segment(part):
                if emit_sfx_cues:
                    cues.extend(_extract_segment_cues(part))
            else:
                # Keep mixed segments as narration but still record obvious cue words.
                if emit_sfx_cues:
                    cues.extend(_extract_segment_cues(part))
                cleaned = _strip_embedded_sfx_tokens(part)
                if cleaned:
                    kept.append(cleaned)
        ln.text = "\n".join(kept).strip()
        ln.sfx_cues = _dedup_keep_order(cues)[:3] if emit_sfx_cues else []
        # Cheap social / platform UI strip (before optional AI polish).
        ln.text = heuristic_clean_social_ui_text(ln.text)
    return lines

