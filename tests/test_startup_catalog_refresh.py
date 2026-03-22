from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


def test_startup_catalog_refresh_blocking(monkeypatch):
    calls = {"count": 0}

    def _fake_crawl():
        calls["count"] += 1
        return {"stats": {"genre_count": 1, "title_count": 1, "episode_count": 1}}

    monkeypatch.setattr(settings, "webtoon_catalog_enabled", True)
    monkeypatch.setattr(settings, "webtoon_catalog_refresh_max_age_hours", 24)
    monkeypatch.setattr("app.main.catalog_is_stale", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.main.crawl_webtoon_catalog", _fake_crawl)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
    assert calls["count"] == 1


def test_startup_catalog_refresh_skips_when_fresh(monkeypatch):
    calls = {"count": 0}

    def _fake_crawl():
        calls["count"] += 1
        return {"stats": {"genre_count": 1, "title_count": 1, "episode_count": 1}}

    monkeypatch.setattr(settings, "webtoon_catalog_enabled", True)
    monkeypatch.setattr(settings, "webtoon_catalog_refresh_max_age_hours", 24)
    monkeypatch.setattr("app.main.catalog_is_stale", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("app.main.crawl_webtoon_catalog", _fake_crawl)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
    assert calls["count"] == 0

