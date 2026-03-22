from app.config import settings as app_settings
from app.models.schemas import SrtTimelineLine
from app.services.audio.scene_segmenter import segment_scenes


def test_scene_segmenter_fallback_covers_all_lines(monkeypatch):
    monkeypatch.setattr(app_settings, "openai_dialogue_analysis_enabled", False)
    lines = [
        SrtTimelineLine(index=i + 1, start_sec=float(i), end_sec=float(i) + 0.8, text=f"line {i+1}", speaker="male_1", emotion="neutral")
        for i in range(12)
    ]
    scenes = segment_scenes(lines)
    assert scenes
    assert scenes[0]["panel_range"][0] == 1
    assert scenes[-1]["panel_range"][1] == len(lines)


def test_scene_segmenter_handles_more_than_300_lines(monkeypatch):
    monkeypatch.setattr(app_settings, "openai_dialogue_analysis_enabled", False)
    monkeypatch.setattr(app_settings, "scene_segment_window_size", 180)
    monkeypatch.setattr(app_settings, "scene_segment_overlap", 20)
    lines = [
        SrtTimelineLine(index=i + 1, start_sec=float(i), end_sec=float(i) + 0.8, text=f"line {i+1}", speaker="male_1", emotion="neutral")
        for i in range(320)
    ]
    scenes = segment_scenes(lines)
    assert scenes
    assert scenes[0]["panel_range"][0] == 1
    assert scenes[-1]["panel_range"][1] == 320
