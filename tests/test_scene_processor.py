from pathlib import Path

from app.models.schemas import SrtTimelineLine
from app.services.audio.episode_state import EpisodeState
from app.services.audio.scene_processor import process_scene


def test_process_scene_uses_refined_emotion_and_rule_music(monkeypatch, tmp_path: Path):
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.2, text="hello", speaker="unknown_1", emotion="neutral", intensity=0.2)
    captured = {"emotion": "", "intensity": -1.0, "music_type": ""}

    monkeypatch.setattr("app.services.audio.scene_processor.analyze_emotion", lambda *_args: ("sad", 0.9))

    def _fake_resolve_audio_plan(_text, emotion, intensity, _scene_type):
        captured["emotion"] = emotion
        captured["intensity"] = intensity
        return {
            "voice_settings": {},
            "speech_mode": "none",
            "sfx_plan": [],
            "music_type": "piano",
            "pause": 0.2,
        }

    monkeypatch.setattr("app.services.audio.scene_processor.resolve_audio_plan", _fake_resolve_audio_plan)

    def _fake_tts(**kwargs):
        Path(kwargs["output_path"]).write_bytes(b"tts")

    def _fake_mix(_events, output_path, _work_dir):
        output_path.write_bytes(b"mix")
        return output_path

    def _fake_resolve_music(_script_lines, _audio_dir, music_type_override=None):
        captured["music_type"] = str(music_type_override or "")
        return None, "none", "disabled"

    out = process_scene(
        scene={"scene_id": 1, "scene_type": "emotional", "scene_emotion": "sad"},
        scene_lines=[line],
        scene_panel_paths=[str(tmp_path / "p.png")],
        scene_audio_dir=tmp_path,
        scene_start_sec=0.0,
        episode_state=EpisodeState(),
        tts_func=_fake_tts,
        mix_func=_fake_mix,
        resolve_music_func=_fake_resolve_music,
        probe_func=lambda _p: 1.0,
    )

    assert out["audio"]
    assert captured["emotion"] == "sad"
    assert 0.6 <= captured["intensity"] <= 0.9
    assert captured["music_type"] == "piano"
