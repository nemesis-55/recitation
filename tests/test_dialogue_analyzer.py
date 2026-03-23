from app.models.schemas import SrtTimelineLine
from app.services.audio import dialogue_analyzer as da
from app.services.audio.dialogue_analyzer import _enforce_speaker_consistency, _normalize_chunk_rows, analyze_srt_timeline


def test_normalize_chunk_rows_truncates_oversized_response():
    rows = [{"speaker": "narrator"} for _ in range(6)]
    normalized = _normalize_chunk_rows(rows, expected_len=1)
    assert len(normalized) == 1
    assert normalized[0]["speaker"] == "narrator"


def test_normalize_chunk_rows_pads_undersized_response():
    rows = [{"speaker": "male_1"}]
    normalized = _normalize_chunk_rows(rows, expected_len=3)
    assert len(normalized) == 3
    assert normalized[0]["speaker"] == "male_1"
    assert normalized[1] == {}
    assert normalized[2] == {}


def test_enforce_speaker_consistency_flips_same_gender_on_turn_markers():
    lines = [
        SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="- Get ready."),
        SrtTimelineLine(index=2, start_sec=1.0, end_sec=2.0, text="- I am ready."),
        SrtTimelineLine(index=3, start_sec=2.0, end_sec=3.0, text="- Move now."),
    ]
    rows = [
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
    ]
    fixed = _enforce_speaker_consistency(rows, lines)
    assert fixed[0]["speaker"] == "male_1"
    assert fixed[1]["speaker"] == "male_2"


def test_analyze_srt_timeline_uses_cache_without_openai(monkeypatch):
    monkeypatch.setattr(da.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(da.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        da,
        "read_cache_json",
        lambda _ns, _key: [{"speaker": "male_1", "emotion": "happy", "intensity": 0.73}],
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(da, "OpenAI", _NeverClient)
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="hello")
    out = analyze_srt_timeline([line])
    assert out[0].speaker == "male_1"
    assert out[0].emotion == "happy"
    assert out[0].intensity == 0.73


def test_analyze_srt_timeline_accepts_urgent_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(da.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(da.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        da,
        "read_cache_json",
        lambda _ns, _key: [{"speaker": "male_1", "emotion": "urgent", "intensity": 0.82}],
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(da, "OpenAI", _NeverClient)
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Move now!")
    out = analyze_srt_timeline([line])
    assert out[0].emotion == "urgent"
    assert out[0].intensity == 0.82


def test_analyze_srt_timeline_accepts_serious_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(da.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(da.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        da,
        "read_cache_json",
        lambda _ns, _key: [{"speaker": "male_1", "emotion": "serious", "intensity": 0.55}],
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(da, "OpenAI", _NeverClient)
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Listen carefully.")
    out = analyze_srt_timeline([line])
    assert out[0].emotion == "serious"
    assert out[0].intensity == 0.55


def test_analyze_srt_timeline_accepts_desperate_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(da.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(da.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        da,
        "read_cache_json",
        lambda _ns, _key: [{"speaker": "female_1", "emotion": "desperate", "intensity": 0.81}],
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(da, "OpenAI", _NeverClient)
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Please... you have to help me!")
    out = analyze_srt_timeline([line])
    assert out[0].emotion == "desperate"
    assert out[0].intensity == 0.81


def test_analyze_srt_timeline_accepts_hopeful_emotion_from_cache(monkeypatch):
    monkeypatch.setattr(da.settings, "openai_dialogue_analysis_enabled", True)
    monkeypatch.setattr(da.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        da,
        "read_cache_json",
        lambda _ns, _key: [{"speaker": "female_1", "emotion": "hopeful", "intensity": 0.61}],
    )

    class _NeverClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI should not be called on cache hit")

    monkeypatch.setattr(da, "OpenAI", _NeverClient)
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="We can still do this")
    out = analyze_srt_timeline([line])
    assert out[0].speaker == "female_1"
    assert out[0].emotion == "hopeful"
    assert out[0].intensity == 0.61
