from __future__ import annotations

import json
from pathlib import Path

from app.config import settings as app_settings
from app.models.schemas import ScriptLine
from app.services.audio import audio_pipeline as ap
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


def test_strict_per_line_tts_one_group_per_line(monkeypatch):
    monkeypatch.setattr(app_settings, "audio_strict_per_line_tts", True)
    monkeypatch.setattr(app_settings, "audio_grouping_enabled", True)
    lines = [
        ScriptLine(panel_path="a", narration="one", speaker="male_1", gender="male", emotion="neutral"),
        ScriptLine(panel_path="b", narration="two", speaker="male_1", gender="male", emotion="neutral"),
    ]
    groups = ap._build_tts_groups(lines)
    assert groups == [[0], [1]]


def test_grouping_disabled_one_per_line(monkeypatch):
    monkeypatch.setattr(app_settings, "audio_strict_per_line_tts", False)
    monkeypatch.setattr(app_settings, "audio_grouping_enabled", False)
    lines = [
        ScriptLine(panel_path="a", narration="one", speaker="male_1", gender="male", emotion="neutral"),
        ScriptLine(panel_path="b", narration="two", speaker="male_1", gender="male", emotion="neutral"),
    ]
    groups = ap._build_tts_groups(lines)
    assert groups == [[0], [1]]


def test_pick_sfx_emotion_file(tmp_path: Path):
    (tmp_path / "breath_light.mp3").write_bytes(b"x")
    line = ScriptLine(panel_path="p", narration="Hello", emotion="fear")
    paths = pick_sfx(line, tmp_path)
    assert paths and paths[0].name == "breath_light.mp3"


def test_pick_sfx_exertion_keyword(tmp_path: Path):
    (tmp_path / "breath_heavy.mp3").write_bytes(b"x")
    line = ScriptLine(panel_path="p", narration="huu", emotion="neutral")
    paths = pick_sfx(line, tmp_path)
    assert any(p.name == "breath_heavy.mp3" for p in paths)


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


def test_resolve_music_bed_local_map(monkeypatch, tmp_path: Path):
    bed = tmp_path / "bed.mp3"
    bed.write_bytes(b"x")
    monkeypatch.setattr(app_settings, "audio_bed_in_narration", True)
    monkeypatch.setattr(app_settings, "audio_music_local_map_json", json.dumps({"neutral": str(bed)}))
    monkeypatch.setattr(app_settings, "audio_use_bgm_default_as_bed", False)
    lines = [ScriptLine(panel_path="p", narration="x", emotion="neutral")]
    path, src, _ = resolve_music_bed(lines, tmp_path)
    assert path == bed.resolve() and src == "local_map"


def test_voice_map_override(monkeypatch):
    monkeypatch.setattr(app_settings, "elevenlabs_voice_map_json", '{"male_1": "voice_override_123"}')
    line = ScriptLine(panel_path="p", narration="hi", speaker="male_1", gender="male", emotion="neutral")
    assert get_voice(line, 0) == "voice_override_123"


def test_resolved_characters_uses_line_voice():
    a = ScriptLine(panel_path="p", narration="a", speaker="female_1", gender="female", emotion="neutral", voice="vid-a")
    b = ScriptLine(panel_path="p2", narration="b", speaker="female_1", gender="female", emotion="happy", voice="vid-b")
    m = resolved_characters([a, b])
    assert m["female_1"] == "vid-b"
