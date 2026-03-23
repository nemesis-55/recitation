from fastapi.testclient import TestClient

from app.main import app


def test_ops_dashboard_route():
    client = TestClient(app)
    response = client.get("/ops")
    assert response.status_code == 200
    assert "Pipeline Ops" in response.text
    assert "SRT" in response.text and "narration" in response.text
    assert "Stage planner" in response.text
    assert "Episodes" in response.text


def test_ops_runs_api_route():
    client = TestClient(app)
    response = client.get("/ops/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()


def test_ops_reel_master_file_route(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.ops.settings.output_root", tmp_path)
    run = tmp_path / "runs" / "genre" / "title-slug" / "ep-0"
    (run / "final").mkdir(parents=True)
    (run / "final" / "video_reel.mp4").write_bytes(b"%fmp4reel")
    client = TestClient(app)
    response = client.get("/ops/api/runs/genre/title-slug/ep-0/files/reel")
    assert response.status_code == 200
    assert response.content.startswith(b"%fmp4reel")


def test_ops_reel_master_file_route_404(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.ops.settings.output_root", tmp_path)
    run = tmp_path / "runs" / "genre" / "title-slug" / "ep-0"
    (run / "final").mkdir(parents=True)
    client = TestClient(app)
    response = client.get("/ops/api/runs/genre/title-slug/ep-0/files/reel")
    assert response.status_code == 404
