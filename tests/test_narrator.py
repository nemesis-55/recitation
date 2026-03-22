from app.config import settings as app_settings
from app.models.schemas import ScriptLine
from app.services.audio.character_engine import get_character_profile, get_voice
from app.services.audio.dialogue_analyzer import estimate_emotion_intensity
from app.services.audio.pause_engine import pause_seconds
from app.services.audio.speech_renderer import render_speech


def test_select_elevenlabs_voice_uses_gender_defaults():
    male_line = ScriptLine(panel_path="p1", narration="hello", gender="male", emotion="neutral")
    female_line = ScriptLine(panel_path="p2", narration="hello", gender="female", emotion="neutral")
    unknown_line = ScriptLine(panel_path="p3", narration="hello", gender="unknown", emotion="neutral")
    assert get_voice(male_line, 0)
    assert get_voice(female_line, 1)
    assert get_voice(unknown_line, 0)


def test_select_elevenlabs_voice_prefers_narrator():
    line = ScriptLine(panel_path="p1", narration="hello", speaker="narrator", gender="male", emotion="angry")
    narrator_voice = get_voice(line, 0)
    assert narrator_voice


def test_select_elevenlabs_voice_for_unknown_uses_unknown_voice():
    line = ScriptLine(panel_path="p1", narration="hello", gender="unknown", emotion="neutral")
    voice_even = get_voice(line, 0)
    voice_odd = get_voice(line, 1)
    assert voice_even == app_settings.elevenlabs_voice_unknown
    assert voice_odd == app_settings.elevenlabs_voice_unknown


def test_select_elevenlabs_voice_inferrs_gender_from_speaker_token():
    male_line = ScriptLine(panel_path="p1", narration="hello", speaker="male_1", gender="unknown", emotion="neutral")
    female_line = ScriptLine(panel_path="p2", narration="hello", speaker="female_2", gender="unknown", emotion="neutral")
    assert get_voice(male_line, 0) != get_voice(female_line, 0)


def test_select_elevenlabs_voice_supports_secondary_same_gender_slots(monkeypatch):
    monkeypatch.setattr(app_settings, "elevenlabs_voice_male_2", "male_voice_alt_2")
    monkeypatch.setattr(app_settings, "elevenlabs_voice_male_7", "male_voice_alt_7")
    monkeypatch.setattr(app_settings, "elevenlabs_voice_female_2", "female_voice_alt_2")
    monkeypatch.setattr(app_settings, "elevenlabs_voice_female_3", "female_voice_alt_3")
    male_1 = ScriptLine(panel_path="p1", narration="hello", speaker="male_1", gender="unknown", emotion="neutral")
    male_2 = ScriptLine(panel_path="p2", narration="hello", speaker="male_2", gender="unknown", emotion="neutral")
    male_7 = ScriptLine(panel_path="p7", narration="hello", speaker="male_7", gender="unknown", emotion="neutral")
    female_1 = ScriptLine(panel_path="p3", narration="hello", speaker="female_1", gender="unknown", emotion="neutral")
    female_2 = ScriptLine(panel_path="p4", narration="hello", speaker="female_2", gender="unknown", emotion="neutral")
    female_3 = ScriptLine(panel_path="p5", narration="hello", speaker="female_3", gender="unknown", emotion="neutral")
    assert get_voice(male_1, 0) == app_settings.elevenlabs_voice_male
    assert get_voice(male_2, 0) == "male_voice_alt_2"
    assert get_voice(male_7, 0) == "male_voice_alt_7"
    assert get_voice(female_1, 0) == app_settings.elevenlabs_voice_female
    assert get_voice(female_2, 0) == "female_voice_alt_2"
    assert get_voice(female_3, 0) == "female_voice_alt_3"


def test_character_profile_contains_voice_direction_keys():
    line = ScriptLine(panel_path="p1", narration="hello", speaker="male_1", gender="male", emotion="neutral")
    profile = get_character_profile(line, 0)
    assert set(profile.keys()) == {"stability", "similarity_boost", "style", "speed"}


def test_render_performance_text_adds_punctuation():
    assert render_speech("hello world", "neutral", 0.4).endswith(".")


def test_render_performance_text_drops_short_sfx_noise():
    assert render_speech("swoosh slash", "neutral", 0.5) == ""


def test_intensity_and_pause_change_by_emotion():
    fear_intensity = estimate_emotion_intensity("I... can't do this!", "fear")
    angry_intensity = estimate_emotion_intensity("MOVE NOW!", "angry")
    assert 0.0 <= fear_intensity <= 1.0
    assert 0.0 <= angry_intensity <= 1.0
    assert pause_seconds("fear", fear_intensity) > pause_seconds("angry", angry_intensity)

