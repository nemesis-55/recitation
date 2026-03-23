from app.config import settings
from app.services.webtoon_catalog_crawler import _genre_urls


def test_genre_urls_accepts_json_array(monkeypatch):
    monkeypatch.setattr(
        settings,
        "webtoon_catalog_genre_urls_json",
        '["https://www.webtoons.com/en/action","https://www.webtoons.com/en/romance"]',
    )
    urls = _genre_urls()
    assert urls == ["https://www.webtoons.com/en/action", "https://www.webtoons.com/en/romance"]


def test_genre_urls_accepts_json_object_values(monkeypatch):
    monkeypatch.setattr(
        settings,
        "webtoon_catalog_genre_urls_json",
        '{"action":"https://www.webtoons.com/en/action","romance":"https://www.webtoons.com/en/romance"}',
    )
    urls = _genre_urls()
    assert urls == ["https://www.webtoons.com/en/action", "https://www.webtoons.com/en/romance"]


def test_genre_urls_accepts_single_json_string(monkeypatch):
    monkeypatch.setattr(settings, "webtoon_catalog_genre_urls_json", '"https://www.webtoons.com/en/action"')
    urls = _genre_urls()
    assert urls == ["https://www.webtoons.com/en/action"]
