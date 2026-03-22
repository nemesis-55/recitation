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


def test_timeline_includes_pause_and_merges_panel_narration():
    panels = [PanelAsset(page_index=1, panel_index=1, image_path="p1.png", bbox=(0, 0, 100, 100))]
    lines = [
        ScriptLine(panel_path="p1.png", narration="First"),
        ScriptLine(panel_path="p1.png", narration="Second"),
    ]
    audio = [
        AudioSegment(line_index=0, audio_path="a1.mp3", start_sec=0.0, end_sec=1.0, duration_sec=1.0, pause_sec=0.2),
        AudioSegment(line_index=1, audio_path="a2.mp3", start_sec=1.2, end_sec=2.0, duration_sec=0.8, pause_sec=0.1),
    ]
    timeline = build_timeline(panels, lines, audio)
    assert len(timeline) == 1
    assert timeline[0].narration == "First Second"
    assert timeline[0].duration_sec == 2.1
