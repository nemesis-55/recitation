from app.config import settings as app_settings
from app.models.schemas import SrtTimelineLine
from app.services.audio import scene_segmenter as ss
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


def test_segment_chunk_converts_local_ranges_to_global(monkeypatch):
    monkeypatch.setattr(app_settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(app_settings, "openai_api_key", "test-key")

    class _FakeResp:
        output_text = '[{"scene_id": 1, "panel_range": [1, 5], "description": "a"}, {"scene_id": 2, "panel_range": [6, 10], "description": "b"}]'

    class _FakeResponses:
        @staticmethod
        def create(**_kwargs):
            return _FakeResp()

    class _FakeClient:
        responses = _FakeResponses()

        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    monkeypatch.setattr(ss, "OpenAI", _FakeClient)
    lines = [
        SrtTimelineLine(index=i + 1, start_sec=float(i), end_sec=float(i) + 0.8, text=f"line {i+1}", speaker="male_1", emotion="neutral")
        for i in range(10)
    ]
    out = ss._segment_chunk(lines, chunk_start=100, expected_total=320)
    assert out[0]["panel_range"] == [101, 105]
    assert out[1]["panel_range"] == [106, 110]
