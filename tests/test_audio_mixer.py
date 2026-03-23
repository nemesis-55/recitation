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
    # Music bed preprocessing (default): HPF + dynaudnorm on bed only; voice timing unchanged.
    assert "highpass=f=100" in filter_graph or "highpass=f=" in filter_graph
    assert "dynaudnorm" in filter_graph


def test_mix_audio_builds_voice_anchor_for_delayed_lines(monkeypatch, tmp_path: Path):
    captured = {"command": []}

    def _fake_run_ffmpeg(command, stage, timeout_sec=300):
        _ = stage, timeout_sec
        captured["command"] = command

    monkeypatch.setattr("app.services.audio.audio_mixer.run_ffmpeg", _fake_run_ffmpeg)

    v1 = tmp_path / "line_000.mp3"
    v2 = tmp_path / "line_001.mp3"
    out = tmp_path / "narration.mp3"
    v1.write_bytes(b"v1")
    v2.write_bytes(b"v2")
    events = [
        AudioEvent(type="voice", file=str(v1), start=0.0, duration=1.0, line_index=0),
        AudioEvent(type="voice", file=str(v2), start=10.0, duration=1.0, line_index=1),
    ]

    mix_audio(events, out, tmp_path)

    cmd = captured["command"]
    assert cmd
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[voice_anchor]" in graph
    assert "amix=inputs=3:duration=first:normalize=0[voice_bus]" in graph

