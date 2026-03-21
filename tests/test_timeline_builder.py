from app.models.schemas import AudioSegment, PanelAsset, ScriptLine
from app.services.timeline_builder import build_timeline


def test_timeline_uses_audio_durations_when_available():
    panels = [
        PanelAsset(page_index=1, panel_index=1, image_path="p1.png", bbox=(0, 0, 100, 100)),
        PanelAsset(page_index=1, panel_index=2, image_path="p2.png", bbox=(0, 0, 100, 100)),
    ]
    lines = [
        ScriptLine(panel_path="p1.png", narration="A"),
        ScriptLine(panel_path="p2.png", narration="B"),
    ]
    audio = [
        AudioSegment(line_index=0, audio_path="a1.mp3", start_sec=0.0, end_sec=0.4, duration_sec=0.4),
        AudioSegment(line_index=1, audio_path="a2.mp3", start_sec=0.4, end_sec=12.4, duration_sec=12.0),
    ]

    timeline = build_timeline(panels, lines, audio)
    assert len(timeline) == 2
    assert timeline[0].duration_sec == 0.4
    assert timeline[1].duration_sec == 12.0
