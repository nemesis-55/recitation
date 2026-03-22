from __future__ import annotations

import re
from pathlib import Path

from app.config import settings
from app.models.schemas import SrtTimelineLine
from app.utils.errors import ValidationError

_TIMESTAMP_RE = re.compile(
    r"^\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*$"
)


def _to_seconds(hh: str, mm: str, ss: str, ms: str) -> float:
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + (int(ms) / 1000.0)


def parse_srt_file(path: str | Path) -> list[SrtTimelineLine]:
    srt_path = Path(path)
    if not srt_path.exists():
        raise ValidationError("srt_loader", f"SRT file not found: {srt_path}", "SRT_NOT_FOUND")
    raw = srt_path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    out: list[SrtTimelineLine] = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        idx_line = lines[0].strip()
        ts_line = lines[1].strip()
        text = " ".join(lines[2:]).strip() if len(lines) > 2 else ""
        try:
            idx = int(idx_line)
        except Exception as exc:
            raise ValidationError("srt_loader", f"Invalid SRT index: {idx_line}", "SRT_INVALID_INDEX") from exc
        m = _TIMESTAMP_RE.match(ts_line)
        if not m:
            raise ValidationError("srt_loader", f"Invalid SRT time range: {ts_line}", "SRT_INVALID_TIME_RANGE")
        start = _to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
        end = _to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
        if end <= start:
            raise ValidationError("srt_loader", f"SRT end<=start at index {idx}", "SRT_INVALID_DURATION")
        dur = end - start
        if dur < settings.srt_min_line_duration_sec:
            end = start + settings.srt_min_line_duration_sec
        if dur > settings.srt_max_line_duration_sec:
            end = start + settings.srt_max_line_duration_sec
        out.append(SrtTimelineLine(index=idx, start_sec=start, end_sec=end, text=text))
    if not out:
        raise ValidationError("srt_loader", "SRT has no usable entries", "SRT_EMPTY")
    return out

