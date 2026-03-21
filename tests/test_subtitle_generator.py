from pathlib import Path

from app.models.schemas import TimelineEntry
from app.services.subtitle_generator import generate_subtitles


def test_subtitle_file_creation(tmp_path: Path):
    timeline = [
        TimelineEntry(panel_path="x.png", narration="This is a long subtitle line that should wrap nicely.", start_sec=0, end_sec=3, duration_sec=3),
        TimelineEntry(panel_path="y.png", narration="Second line.", start_sec=3, end_sec=6, duration_sec=3),
    ]
    out_path = tmp_path / "subtitles.srt"
    file_path, entries = generate_subtitles(timeline, out_path)
    assert file_path.exists()
    assert len(entries) == 2
    content = file_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:03,000" in content
