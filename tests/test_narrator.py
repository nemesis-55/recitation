from app.models.schemas import ScriptLine
from app.services.narrator import _normalize_tts_text, _select_voice_for_line, _tts_cache_key_for_line


def test_select_voice_for_line_uses_gender_defaults():
    male_line = ScriptLine(panel_path="p1", narration="hello", gender="male", emotion="neutral")
    female_line = ScriptLine(panel_path="p2", narration="hello", gender="female", emotion="neutral")
    unknown_line = ScriptLine(panel_path="p3", narration="hello", gender="unknown", emotion="neutral")
    assert _select_voice_for_line(male_line, 0)
    assert _select_voice_for_line(female_line, 1)
    assert _select_voice_for_line(unknown_line, 0)


def test_select_voice_for_line_prefers_narrator():
    line = ScriptLine(panel_path="p1", narration="hello", speaker="narrator", gender="male", emotion="angry")
    narrator_voice = _select_voice_for_line(line, 0)
    assert narrator_voice


def test_select_voice_for_unknown_alternates_two_reciters():
    line = ScriptLine(panel_path="p1", narration="hello", gender="unknown", emotion="neutral")
    voice_even = _select_voice_for_line(line, 0)
    voice_odd = _select_voice_for_line(line, 1)
    assert voice_even != voice_odd


def test_tts_cache_key_changes_with_voice():
    line = ScriptLine(panel_path="p1", narration="Hello", gender="male", emotion="happy")
    key_a = _tts_cache_key_for_line("Hello.", line, selected_voice="alloy")
    key_b = _tts_cache_key_for_line("Hello.", line, selected_voice="nova")
    assert key_a != key_b


def test_normalize_tts_text_adds_punctuation():
    assert _normalize_tts_text("hello world", "neutral").endswith(".")
