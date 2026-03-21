from app.models.schemas import ScriptLine
from app.services.narrator import (
    _estimate_emotion_intensity,
    _pause_seconds_for_line,
    _render_performance_text,
    _select_elevenlabs_voice,
    _tts_cache_key_for_line,
)


def test_select_elevenlabs_voice_uses_gender_defaults():
    male_line = ScriptLine(panel_path="p1", narration="hello", gender="male", emotion="neutral")
    female_line = ScriptLine(panel_path="p2", narration="hello", gender="female", emotion="neutral")
    unknown_line = ScriptLine(panel_path="p3", narration="hello", gender="unknown", emotion="neutral")
    assert _select_elevenlabs_voice(male_line, 0)
    assert _select_elevenlabs_voice(female_line, 1)
    assert _select_elevenlabs_voice(unknown_line, 0)


def test_select_elevenlabs_voice_prefers_narrator():
    line = ScriptLine(panel_path="p1", narration="hello", speaker="narrator", gender="male", emotion="angry")
    narrator_voice = _select_elevenlabs_voice(line, 0)
    assert narrator_voice


def test_select_elevenlabs_voice_for_unknown_alternates_two_reciters():
    line = ScriptLine(panel_path="p1", narration="hello", gender="unknown", emotion="neutral")
    voice_even = _select_elevenlabs_voice(line, 0)
    voice_odd = _select_elevenlabs_voice(line, 1)
    assert voice_even != voice_odd


def test_tts_cache_key_changes_with_voice():
    line = ScriptLine(panel_path="p1", narration="Hello", gender="male", emotion="happy")
    key_a = _tts_cache_key_for_line("Hello.", line, selected_voice="alloy", provider="openai")
    key_b = _tts_cache_key_for_line("Hello.", line, selected_voice="nova", provider="openai")
    assert key_a != key_b


def test_tts_cache_key_changes_with_provider():
    line = ScriptLine(panel_path="p1", narration="Hello", gender="male", emotion="happy")
    key_a = _tts_cache_key_for_line("Hello.", line, selected_voice="alloy", provider="elevenlabs")
    key_b = _tts_cache_key_for_line("Hello.", line, selected_voice="alloy", provider="alt-provider")
    assert key_a != key_b


def test_render_performance_text_adds_punctuation():
    assert _render_performance_text("hello world", "neutral", 0.4).endswith(".")


def test_intensity_and_pause_change_by_emotion():
    fear_intensity = _estimate_emotion_intensity("I... can't do this!", "fear")
    angry_intensity = _estimate_emotion_intensity("MOVE NOW!", "angry")
    assert 0.0 <= fear_intensity <= 1.0
    assert 0.0 <= angry_intensity <= 1.0
    assert _pause_seconds_for_line("fear", fear_intensity) > _pause_seconds_for_line("angry", angry_intensity)

