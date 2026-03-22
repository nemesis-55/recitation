from fastapi.testclient import TestClient

from app.main import app


def test_ops_manga_api_route(monkeypatch):
    monkeypatch.setattr(
        "app.routes.ops.search_titles",
        lambda query=None, genre=None, limit=50, offset=0: {"items": [{"title_slug": "omniscient-reader"}], "total": 1},
    )
    client = TestClient(app)
    response = client.get("/ops/api/manga?query=omniscient")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title_slug"] == "omniscient-reader"


def test_ops_manga_episodes_route(monkeypatch):
    monkeypatch.setattr(
        "app.routes.ops.list_episodes",
        lambda title_slug: [{"episode_no": 1, "episode_slug": "episode-1", "viewer_url": "https://www.webtoons.com/x"}],
    )
    client = TestClient(app)
    response = client.get("/ops/api/manga/omniscient-reader/episodes")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["episodes"][0]["episode_no"] == 1


def test_ops_generate_range_route(monkeypatch):
    monkeypatch.setattr(
        "app.routes.ops.run_episode_range_sequential",
        lambda payload: {
            "status": "completed",
            "title_slug": payload.title_slug,
            "submitted": 2,
            "completed": 2,
            "failed": 0,
            "results": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/ops/api/generate-range",
        json={"title_slug": "omniscient-reader", "episode_from": 1, "episode_to": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["submitted"] == 2


def test_ops_generate_range_route_accepts_episode_numbers(monkeypatch):
    monkeypatch.setattr(
        "app.routes.ops.run_episode_range_sequential",
        lambda payload: {
            "status": "completed",
            "title_slug": payload.title_slug,
            "submitted": len(payload.episode_numbers or []),
            "completed": len(payload.episode_numbers or []),
            "failed": 0,
            "results": [],
        },
    )
    client = TestClient(app)
    response = client.post(
        "/ops/api/generate-range",
        json={"title_slug": "omniscient-reader", "episode_numbers": [1, 5, 9]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["submitted"] == 3


def test_ops_generate_range_rejects_deprecated_fields():
    client = TestClient(app)
    response = client.post(
        "/ops/api/generate-range",
        json={"title_slug": "omniscient-reader", "episode_from": 1, "episode_to": 2, "subtitles": True},
    )
    assert response.status_code == 422

