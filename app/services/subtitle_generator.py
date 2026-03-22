from __future__ import annotations

from pathlib import Path

from app.models.schemas import SrtTimelineLine, SubtitleEntry, TimelineEntry
from app.services.audio.srt_timeline import parse_srt_file


def _to_srt_time(seconds: float) -> str:
    ms = int(seconds * 1000)
    hh = ms // 3600000
    mm = (ms % 3600000) // 60000
    ss = (ms % 60000) // 1000
    mss = ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mss:03d}"


def _wrap_text(text: str, max_len: int = 42) -> str:
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        test = " ".join(cur + [w])
        if len(test) > max_len and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:2])


def generate_subtitles(timeline: list[TimelineEntry], out_path: Path) -> tuple[Path, list[SubtitleEntry]]:
    entries: list[SubtitleEntry] = []
    for i, item in enumerate(timeline, start=1):
        wrapped = _wrap_text(item.narration)
        if not wrapped:
            continue
        entries.append(
            SubtitleEntry(
                index=i,
                start_sec=item.start_sec,
                end_sec=item.end_sec,
                text=wrapped,
            )
        )

    chunks = []
    for e in entries:
        chunks.append(f"{e.index}\n{_to_srt_time(e.start_sec)} --> {_to_srt_time(e.end_sec)}\n{e.text}\n")
    out_path.write_text("\n".join(chunks), encoding="utf-8")
    return out_path, entries


def load_srt_timeline(path: str | Path) -> list[SrtTimelineLine]:
    return parse_srt_file(path)
