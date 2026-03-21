from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioEvent:
    type: str
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
