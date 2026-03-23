from app.models.schemas import SrtTimelineLine
from app.services.audio import scene_analyzer as sa
from app.services.audio.scene_analyzer import analyze_scene


def test_scene_analyzer_uses_cache_without_openai(monkeypatch):
    monkeypatch.setattr(sa.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(sa.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        sa,
        "read_cache_json",
        lambda _ns, _key: {"characters": [{"id": "char_1"}], "scene_type": "fight", "scene_emotion": "angry"},
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(sa, "OpenAI", _NeverClient)
    out = analyze_scene([SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Attack now")])
    assert out["scene_type"] == "fight"
    assert out["scene_emotion"] == "angry"
    assert out["characters"] == [{"id": "char_1"}]


def test_scene_analyzer_accepts_nostalgic_scene_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(sa.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(sa.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        sa,
        "read_cache_json",
        lambda _ns, _key: {"characters": [], "scene_type": "emotional", "scene_emotion": "nostalgic"},
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(sa, "OpenAI", _NeverClient)
    out = analyze_scene([SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Those days...")])
    assert out["scene_emotion"] == "nostalgic"


def test_scene_analyzer_accepts_hopeful_scene_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(sa.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(sa.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        sa,
        "read_cache_json",
        lambda _ns, _key: {"characters": [{"id": "char_2"}], "scene_type": "emotional", "scene_emotion": "hopeful"},
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(sa, "OpenAI", _NeverClient)
    out = analyze_scene([SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="There is still hope")])
    assert out["scene_type"] == "emotional"
    assert out["scene_emotion"] == "hopeful"
    assert out["characters"] == [{"id": "char_2"}]
