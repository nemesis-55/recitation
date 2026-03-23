import json
from pathlib import Path

from app.services.ops_observer import get_run_detail, list_runs


def test_ops_observer_lists_runs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.ops_observer._run_roots", lambda: [tmp_path])
    run = tmp_path / "romance" / "dirty-deeds" / "episode-1"
    (run / "meta").mkdir(parents=True)
    (run / "final").mkdir(parents=True)
    (run / "meta" / "job_report.json").write_text(json.dumps({"elapsed_sec": 12.3, "stages": {"pdf_loader": {}}}), encoding="utf-8")
    (run / "final" / "video_youtube.mp4").write_bytes(b"x")

    runs = list_runs(limit=10)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "romance/dirty-deeds/episode-1"
    assert runs[0]["has_video"] is True
    assert runs[0]["status"] == "completed"


def test_ops_observer_run_detail_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.ops_observer._run_roots", lambda: [tmp_path])
    detail = get_run_detail("missing")
    assert detail["exists"] is False


def test_ops_observer_run_detail_includes_reel_master_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.ops_observer._run_roots", lambda: [tmp_path])
    run = tmp_path / "g" / "t" / "episode-1"
    (run / "meta").mkdir(parents=True)
    (run / "final").mkdir(parents=True)
    (run / "meta" / "job_report.json").write_text("{}", encoding="utf-8")
    reel = run / "final" / "video_reel.mp4"
    reel.write_bytes(b"x")
    detail = get_run_detail("g/t/episode-1")
    assert detail["exists"] is True
    assert detail["files"]["reel_video"] == str(reel)
