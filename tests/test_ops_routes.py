from fastapi.testclient import TestClient

from app.main import app


def test_ops_dashboard_route():
    client = TestClient(app)
    response = client.get("/ops")
    assert response.status_code == 200
    assert "Operations Dashboard" in response.text
    assert "SRT Cinematic Analysis" in response.text
    assert "Video Planner & Step Visualizer" in response.text
    assert "Select Episodes (multi-select)" in response.text


def test_ops_runs_api_route():
    client = TestClient(app)
    response = client.get("/ops/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()
