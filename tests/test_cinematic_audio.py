from __future__ import annotations

from pathlib import Path

from app.config import settings as app_settings
from app.models.schemas import ScriptLine
from app.services.audio.character_engine import get_voice, resolved_characters
from app.services.audio.dialogue_analyzer import analyze_dialogue
from app.services.audio.music_engine import estimate_script_narration_duration_sec, music_prompt_for_emotion, resolve_music_bed
from app.services.audio.sfx_engine import pick_sfx


def test_dialogue_analyzer_keeps_llm_intensity():
    line = ScriptLine(panel_path="p", narration="Hi", emotion="fear", emotion_intensity=0.91)
    analyze_dialogue([line])
    assert line.emotion_intensity == 0.91


def test_dialogue_analyzer_fills_missing_intensity():
    line = ScriptLine(panel_path="p", narration="STOP!!!", emotion="angry", emotion_intensity=None)
    analyze_dialogue([line])
    assert line.emotion_intensity is not None
    assert 0.0 <= line.emotion_intensity <= 1.0


def test_pick_sfx_returns_event_marker_for_fear(tmp_path: Path):
    line = ScriptLine(panel_path="p", narration="Hello", emotion="fear")
    paths = pick_sfx(line, tmp_path)
    assert paths and paths[0].as_posix().startswith("event:/fear")


def test_pick_sfx_keyword_hit_maps_event(tmp_path: Path):
    line = ScriptLine(panel_path="p", narration="He lands a punch", emotion="neutral")
    paths = pick_sfx(line, tmp_path)
    assert paths and paths[0].as_posix().startswith("event:/hit")


def test_music_prompt_for_emotion():
    assert "ambient" in music_prompt_for_emotion("neutral").lower() or "soft" in music_prompt_for_emotion("neutral").lower()


def test_estimate_script_narration_duration_positive():
    lines = [
        ScriptLine(panel_path="p", narration="Hello there friend", emotion="neutral", emotion_intensity=0.5),
    ]
    assert estimate_script_narration_duration_sec(lines) >= 5.0


def test_resolve_music_bed_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_settings, "audio_bed_in_narration", False)
    lines = [ScriptLine(panel_path="p", narration="x", emotion="neutral")]
    path, src, reason = resolve_music_bed(lines, tmp_path)
    assert path is None and src == "none"
    assert reason


def test_resolve_music_bed_when_elevenlabs_music_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_settings, "audio_bed_in_narration", True)
    monkeypatch.setattr(app_settings, "elevenlabs_music_enabled", False)
    lines = [ScriptLine(panel_path="p", narration="x", emotion="neutral")]
    path, src, reason = resolve_music_bed(lines, tmp_path)
    assert path is None and src == "none"
    assert reason == "elevenlabs_music_disabled"


def test_voice_map_override(monkeypatch):
    monkeypatch.setattr(app_settings, "elevenlabs_voice_map_json", '{"male_1": "voice_override_123"}')
    line = ScriptLine(panel_path="p", narration="hi", speaker="male_1", gender="male", emotion="neutral")
    assert get_voice(line, 0) == "voice_override_123"


def test_resolved_characters_uses_line_voice():
    a = ScriptLine(panel_path="p", narration="a", speaker="female_1", gender="female", emotion="neutral", voice="vid-a")
    b = ScriptLine(panel_path="p2", narration="b", speaker="female_1", gender="female", emotion="happy", voice="vid-b")
    m = resolved_characters([a, b])
    assert m["female_1"] == "vid-b"
