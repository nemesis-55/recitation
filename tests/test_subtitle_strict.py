from pathlib import Path

from app.models.schemas import TimelineEntry
from app.services.subtitle_generator import generate_subtitles


def test_subtitles_skip_empty_lines(tmp_path: Path):
    timeline = [
        TimelineEntry(panel_path="a.jpg", narration="", start_sec=0, end_sec=2, duration_sec=2),
        TimelineEntry(panel_path="b.jpg", narration="Hello there", start_sec=2, end_sec=4, duration_sec=2),
    ]
    out_path = tmp_path / "strict.srt"
    _, entries = generate_subtitles(timeline, out_path)
    assert len(entries) == 1
    assert entries[0].text == "Hello there"
