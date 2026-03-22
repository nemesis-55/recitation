from pathlib import Path

from app.models.schemas import SrtTimelineLine
from app.services.audio.audio_pipeline import run_audio_pipeline


def test_audio_pipeline_uses_silence_for_empty_text(monkeypatch, tmp_path: Path):
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="")
    panel_paths = [str(tmp_path / "panel.png")]
    (tmp_path / "panel.png").write_bytes(b"x")

    monkeypatch.setattr("app.services.audio.audio_pipeline.analyze_srt_timeline", lambda lines: lines)
    monkeypatch.setattr("app.services.audio.audio_pipeline.get_voice", lambda _sl, _idx: "voice_1")
    monkeypatch.setattr("app.services.audio.audio_pipeline.resolve_music_bed", lambda _script, _audio_dir: (None, "none", "disabled"))

    def _fake_run_ffmpeg(command, stage, timeout_sec=300):
        _ = stage, timeout_sec
        Path(command[-1]).write_bytes(b"silence")

    monkeypatch.setattr("app.services.audio.audio_pipeline.run_ffmpeg", _fake_run_ffmpeg)
    monkeypatch.setattr("app.services.audio.audio_pipeline.generate_tts", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("TTS should not run for empty text")))
    monkeypatch.setattr(
        "app.services.audio.audio_pipeline.mix_audio",
        lambda events, output_path, work_dir: (output_path.write_bytes(b"mix"), output_path)[1],
    )

    narration_path, segments, timeline, meta = run_audio_pipeline([line], tmp_path, panel_paths=panel_paths)

    assert narration_path.exists()
    assert segments[0].rendered_text == ""
    assert segments[0].duration_sec == 2.0
    assert timeline[0]["type"] == "voice"
    assert meta["sfx_source"] == "disabled"


def test_audio_pipeline_avoids_voice_overlap(monkeypatch, tmp_path: Path):
    lines = [
        SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="first line"),
        SrtTimelineLine(index=2, start_sec=1.0, end_sec=3.0, text="second line"),
    ]
    panel_paths = [str(tmp_path / "p1.png"), str(tmp_path / "p2.png")]
    (tmp_path / "p1.png").write_bytes(b"x")
    (tmp_path / "p2.png").write_bytes(b"y")

    monkeypatch.setattr("app.services.audio.audio_pipeline.analyze_srt_timeline", lambda items: items)
    monkeypatch.setattr("app.services.audio.audio_pipeline.get_voice", lambda _sl, _idx: "voice_1")
    monkeypatch.setattr("app.services.audio.audio_pipeline.resolve_music_bed", lambda _script, _audio_dir: (None, "none", "disabled"))
    monkeypatch.setattr("app.services.audio.audio_pipeline.generate_tts", lambda **kwargs: Path(kwargs["output_path"]).write_bytes(b"tts"))
    monkeypatch.setattr("app.services.audio.audio_pipeline.probe_duration_seconds", lambda _p: 2.0)

    captured = {"events": []}

    def _fake_mix_audio(events, output_path, work_dir):
        _ = work_dir
        captured["events"] = events
        output_path.write_bytes(b"mix")
        return output_path

    monkeypatch.setattr("app.services.audio.audio_pipeline.mix_audio", _fake_mix_audio)

    narration_path, segments, timeline, _meta = run_audio_pipeline(lines, tmp_path, panel_paths=panel_paths)

    assert narration_path.exists()
    assert len(captured["events"]) >= 2
    first = captured["events"][0]
    second = captured["events"][1]
    assert first.type == "voice" and second.type == "voice"
    assert first.start + first.duration <= second.start + 1e-6
    assert segments[0].end_sec <= segments[1].start_sec + 1e-6
    assert timeline[0]["duration"] >= 2.0 - 1e-6
