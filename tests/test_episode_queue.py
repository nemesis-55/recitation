from app.models.schemas import EpisodeRangeGenerateRequest, GenerateResponse
from app.services.episode_queue import run_episode_range_sequential


def test_episode_queue_selects_explicit_episode_numbers(monkeypatch):
    monkeypatch.setattr(
        "app.services.episode_queue.list_episodes",
        lambda _slug: [
            {"episode_no": 1, "episode_slug": "ep-1", "viewer_url": "u1"},
            {"episode_no": 2, "episode_slug": "ep-2", "viewer_url": "u2"},
            {"episode_no": 3, "episode_slug": "ep-3", "viewer_url": "u3"},
        ],
    )
    monkeypatch.setattr(
        "app.services.episode_queue.generate_video",
        lambda _req: GenerateResponse(status="completed", video_path="/tmp/v.mp4"),
    )
    payload = EpisodeRangeGenerateRequest(title_slug="x", episode_numbers=[1, 3], subtitles=True)
    out = run_episode_range_sequential(payload)
    assert out.status == "completed"
    assert out.submitted == 2
    assert [r["episode_no"] for r in out.results] == [1, 3]


def test_episode_queue_rejects_panel_filters_for_multi_episode(monkeypatch):
    monkeypatch.setattr(
        "app.services.episode_queue.list_episodes",
        lambda _slug: [
            {"episode_no": 1, "episode_slug": "ep-1", "viewer_url": "u1"},
            {"episode_no": 2, "episode_slug": "ep-2", "viewer_url": "u2"},
        ],
    )
    called = {"count": 0}

    def _fake_generate(_req):
        called["count"] += 1
        return GenerateResponse(status="completed", video_path="/tmp/v.mp4")

    monkeypatch.setattr("app.services.episode_queue.generate_video", _fake_generate)
    payload = EpisodeRangeGenerateRequest(
        title_slug="x",
        select_all_episodes=True,
        panel_from=1,
        panel_to=10,
        subtitles=True,
    )
    out = run_episode_range_sequential(payload)
    assert out.status == "failed"
    assert out.results and out.results[0]["error_code"] == "PANEL_FILTER_SINGLE_EPISODE_ONLY"
    assert called["count"] == 0


def test_episode_queue_auto_chunk_stitches(monkeypatch, tmp_path):
    run_root = tmp_path / "run_ep1"
    (run_root / "final").mkdir(parents=True, exist_ok=True)
    (run_root / "meta").mkdir(parents=True, exist_ok=True)
    chunk1 = run_root / "final" / "chunk1.mp4"
    chunk2 = run_root / "final" / "chunk2.mp4"
    chunk1.write_bytes(b"c1")
    chunk2.write_bytes(b"c2")
    report_path = run_root / "meta" / "job_report.json"
    report_path.write_text("{}", encoding="utf-8")
    calls = {"count": 0}

    def _fake_generate(_req):
        calls["count"] += 1
        if calls["count"] == 1:
            return GenerateResponse(status="completed", video_path=str(chunk1), report_path=str(report_path))
        if calls["count"] == 2:
            return GenerateResponse(status="completed", video_path=str(chunk2), report_path=str(report_path))
        return GenerateResponse(status="failed", error_code="PANEL_RANGE_EMPTY", error="done")

    def _fake_stitch(command, stage, timeout_sec=300):
        _ = stage, timeout_sec
        out = command[-1]
        from pathlib import Path as _P

        _P(out).write_bytes(b"stitched")

    monkeypatch.setattr("app.services.episode_queue.generate_video", _fake_generate)
    monkeypatch.setattr("app.services.episode_queue.run_ffmpeg", _fake_stitch)
    monkeypatch.setattr("app.services.episode_queue.list_episodes", lambda _slug: [{"episode_no": 1, "episode_slug": "ep-1", "viewer_url": "u1"}])
    monkeypatch.setattr("app.services.episode_queue.settings.auto_chunk_enabled", True)
    monkeypatch.setattr("app.services.episode_queue.settings.auto_chunk_stitch", True)
    monkeypatch.setattr("app.services.episode_queue.settings.auto_chunk_max_panels", 80)
    monkeypatch.setattr("app.services.episode_queue.settings.auto_chunk_max_chunks", 10)

    out = run_episode_range_sequential(EpisodeRangeGenerateRequest(title_slug="x", episode_numbers=[1], subtitles=True))
    assert out.status == "completed"
    assert out.results[0]["video_path"].endswith("/video_full.mp4")
