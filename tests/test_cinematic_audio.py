from __future__ import annotations

from pathlib import Path

from app.config import settings as app_settings
from app.models.schemas import ScriptLine
from app.services.audio.character_engine import get_voice, resolved_characters
from app.services.audio.dialogue_analyzer import analyze_dialogue
from app.services.audio.bgm_library import pick_bgm_slot
from app.services.audio.music_engine import estimate_script_narration_duration_sec, music_prompt_for_emotion, resolve_music_bed
from app.services.audio.sfx_alignment_engine import align_sfx
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
    assert paths and paths[0].as_posix().startswith("event:/light_breath")


def test_pick_sfx_keyword_hit_maps_event(tmp_path: Path):
    line = ScriptLine(panel_path="p", narration="He lands a punch", emotion="neutral")
    paths = pick_sfx(line, tmp_path)
    assert paths and paths[0].as_posix().startswith("event:/impact")


def test_align_sfx_normalizes_noisy_ocr_tokens():
    out = align_sfx("fwoosh woooosh shhhh", 1.6, "movement")
    assert out["sfx"] == "footsteps.mp3"
    assert float(out["timestamp"]) >= 0.0


def test_music_prompt_for_emotion():
    assert "ambient" in music_prompt_for_emotion("neutral").lower() or "soft" in music_prompt_for_emotion("neutral").lower()


def test_pick_bgm_slot_maps_emotion_to_family_not_random_mod(monkeypatch):
    """Large library counts must not scatter moods across unrelated slots."""
    monkeypatch.setattr("app.services.audio.bgm_library.bgm_library_count", lambda: 40)
    sad_slots = {pick_bgm_slot("sad", scene_id=i, line_count=3) for i in range(50)}
    assert sad_slots.issubset({1, 11, 21, 31}), f"expected sad family 1+10k, got {sad_slots}"
    angry_slots = {pick_bgm_slot("angry", scene_id=i, line_count=1) for i in range(50)}
    assert angry_slots.issubset({8, 18, 28, 38}), f"expected angry family 8+10k, got {angry_slots}"


def test_pick_bgm_slot_small_count_falls_back(monkeypatch):
    monkeypatch.setattr("app.services.audio.bgm_library.bgm_library_count", lambda: 5)
    # family 7 (weak) has no row <5 — must still return a valid slot via fallback
    s = pick_bgm_slot("weak", scene_id=0, line_count=1)
    assert 0 <= s < 5


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
    lib = tmp_path / "lib"
    lib.mkdir()
    slot_file = lib / "bgm_00.mp3"
    slot_file.write_bytes(b"fakeaudio")
    monkeypatch.setattr(app_settings, "bgm_library_dir", str(lib))
    monkeypatch.setattr(app_settings, "bgm_library_prefer_local", True)
    lines = [ScriptLine(panel_path="p", narration="x", emotion="neutral")]
    path, src, reason = resolve_music_bed(lines, tmp_path, scene_id=0)
    assert path is not None and path.exists()
    assert src == "bgm_library"
    assert "slot_" in reason


def test_resolve_music_bed_prefers_rule_music_type(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_settings, "audio_bed_in_narration", True)
    monkeypatch.setattr(app_settings, "elevenlabs_music_enabled", True)
    monkeypatch.setattr(app_settings, "bgm_library_prefer_local", False)
    captured = {"prompt": ""}

    def _fake_generate_scene_music(prompt: str, duration_ms: int, output_path: Path):
        _ = duration_ms
        captured["prompt"] = prompt
        output_path.write_bytes(b"music")

    monkeypatch.setattr("app.services.audio.music_engine.generate_scene_music", _fake_generate_scene_music)
    lines = [ScriptLine(panel_path="p", narration="soft line", emotion="neutral")]
    path, src, reason = resolve_music_bed(lines, tmp_path, music_type_override="intense")
    assert path is not None and path.exists()
    assert src == "elevenlabs" and reason == ""
    assert "aggressive strings" in captured["prompt"].lower() or "action tension" in captured["prompt"].lower()


def test_voice_map_override(monkeypatch):
    monkeypatch.setattr(app_settings, "elevenlabs_voice_map_json", '{"male_1": "voice_override_123"}')
    line = ScriptLine(panel_path="p", narration="hi", speaker="male_1", gender="male", emotion="neutral")
    assert get_voice(line, 0) == "voice_override_123"


def test_resolved_characters_uses_line_voice():
    a = ScriptLine(panel_path="p", narration="a", speaker="female_1", gender="female", emotion="neutral", voice="vid-a")
    b = ScriptLine(panel_path="p2", narration="b", speaker="female_1", gender="female", emotion="happy", voice="vid-b")
    m = resolved_characters([a, b])
    assert m["female_1"] == "vid-b"
