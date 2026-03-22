from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class AudioEvent:
    type: Literal["voice", "pause", "sfx", "music"]
    file: str
    start: float
    duration: float
    line_index: int


def build_timeline(events: list[AudioEvent]) -> list[dict]:
    return [
        {
            "type": e.type,
            "file": e.file,
            "start": round(e.start, 3),
            "duration": round(e.duration, 3),
            "line_index": e.line_index,
        }
        for e in events
    ]


def build_cinematic_timeline(
    voice_events: list[AudioEvent], sfx_events: list[AudioEvent], music_event: AudioEvent | None = None
) -> list[AudioEvent]:
    out: list[AudioEvent] = []
    out.extend(voice_events)
    out.extend(sfx_events)
    if music_event is not None:
        out.append(music_event)
    out.sort(key=lambda e: (e.start, 0 if e.type == "music" else 1))
    return out
