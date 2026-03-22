from pathlib import Path

from app.models.schemas import AudioSegment, SrtTimelineLine
from app.services.audio.audio_pipeline import run_audio_pipeline


def test_audio_pipeline_keeps_ai_scene_type_and_emotion(monkeypatch, tmp_path: Path):
    line = SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="dialogue", emotion="neutral", intensity=0.4)
    panel_path = tmp_path / "panel.png"
    panel_path.write_bytes(b"x")
    captured = {"scene_type": "", "scene_emotion": ""}

    monkeypatch.setattr("app.services.audio.audio_pipeline.analyze_srt_timeline", lambda items: items)
    monkeypatch.setattr(
        "app.services.audio.audio_pipeline.analyze_scene",
        lambda _lines: {"scene_type": "fight", "scene_emotion": "fear", "characters": []},
    )
    monkeypatch.setattr(
        "app.services.audio.audio_pipeline.segment_scenes",
        lambda _lines: [{"scene_id": 1, "panel_range": [1, 1], "scene_type": "fight", "scene_emotion": "fear"}],
    )

    def _fake_process_scene(scene, *_args):
        captured["scene_type"] = str(scene.get("scene_type", ""))
        captured["scene_emotion"] = str(scene.get("scene_emotion", ""))
        out = tmp_path / "scene_001.mp3"
        out.write_bytes(b"audio")
        seg = AudioSegment(
            line_index=0,
            audio_path=str(out),
            start_sec=0.0,
            end_sec=1.0,
            duration_sec=1.0,
            pause_sec=0.0,
            provider="elevenlabs",
        )
        return {
            "scene_id": 1,
            "audio": str(out),
            "timeline": [{"type": "voice", "file": str(out), "start": 0.0, "duration": 1.0, "line_index": 0}],
            "segments": [seg],
            "duration": 1.0,
        }

    monkeypatch.setattr("app.services.audio.audio_pipeline.process_scene", _fake_process_scene)

    narration_path, segments, timeline, meta = run_audio_pipeline([line], tmp_path, panel_paths=[str(panel_path)])

    assert narration_path.exists()
    assert segments and timeline
    assert captured["scene_type"] == "fight"
    assert captured["scene_emotion"] == "fear"
    assert meta["scene_type"] == "fight"
    assert meta["scene_emotion"] == "fear"
