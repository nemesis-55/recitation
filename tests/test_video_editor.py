from pathlib import Path

from app.services.video_editor import split_video_chunks


def test_split_video_chunks_respects_max_duration(monkeypatch, tmp_path: Path):
    source = tmp_path / "reel.mp4"
    source.write_bytes(b"video")
    out_dir = tmp_path / "chunks"
    created: list[Path] = []

    monkeypatch.setattr("app.services.video_editor.probe_duration_seconds", lambda _p: 130.0)

    def _fake_run_ffmpeg(cmd, stage, timeout_sec=300):
        _ = stage, timeout_sec
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"chunk")
        created.append(out)

    monkeypatch.setattr("app.services.video_editor.run_ffmpeg", _fake_run_ffmpeg)
    chunks = split_video_chunks(source, out_dir, max_duration_sec=60.0)
    assert [p.name for p in chunks] == ["reel_chunk_001.mp4", "reel_chunk_002.mp4", "reel_chunk_003.mp4"]
    assert created == chunks
