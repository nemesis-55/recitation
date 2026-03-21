from fastapi.testclient import TestClient

from app.main import app


def test_ops_dashboard_route():
    client = TestClient(app)
    response = client.get("/ops")
    assert response.status_code == 200
    assert "Operations Dashboard" in response.text
    assert "OpenAI Narration" in response.text
    assert "Max Panels to Evaluate" in response.text


def test_ops_runs_api_route():
    client = TestClient(app)
    response = client.get("/ops/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()
