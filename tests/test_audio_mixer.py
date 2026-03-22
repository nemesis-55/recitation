from pathlib import Path

from app.services.audio.audio_mixer import mix_audio
from app.services.audio.timeline_builder import AudioEvent


def test_mix_audio_uses_bounded_output_and_first_duration_for_music(monkeypatch, tmp_path: Path):
    captured = {"command": []}

    def _fake_run_ffmpeg(command, stage, timeout_sec=300):
        _ = stage, timeout_sec
        captured["command"] = command

    monkeypatch.setattr("app.services.audio.audio_mixer.run_ffmpeg", _fake_run_ffmpeg)

    voice = tmp_path / "line_000.mp3"
    music = tmp_path / "music_scene.mp3"
    out = tmp_path / "narration.mp3"
    voice.write_bytes(b"v")
    music.write_bytes(b"m")

    events = [AudioEvent(type="voice", file=str(voice), start=0.0, duration=3.0, line_index=0)]
    mix_audio(events, out, tmp_path, music_path=music)

    command = captured["command"]
    assert command
    assert "-t" in command
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "duration=first" in filter_graph
    assert "atrim=0:" in filter_graph
    assert "apad" not in filter_graph

