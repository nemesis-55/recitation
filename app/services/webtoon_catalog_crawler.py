from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings
from app.services.manga_catalog import empty_catalog, save_catalog
from app.utils.errors import ValidationError

logger = logging.getLogger(__name__)


def _slug(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "unknown"


def _genre_urls() -> list[str]:
    raw = settings.webtoon_catalog_genre_urls_json
    if not raw:
        raise ValidationError(
            "catalog_crawler",
            "WEBTOON_CATALOG_GENRE_URLS_JSON is required for crawl bootstrap.",
            "CATALOG_MISSING_GENRE_URLS",
        )
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValidationError("catalog_crawler", f"Invalid WEBTOON_CATALOG_GENRE_URLS_JSON: {exc}", "CATALOG_BAD_GENRE_URLS") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValidationError("catalog_crawler", "WEBTOON_CATALOG_GENRE_URLS_JSON must be a non-empty array", "CATALOG_BAD_GENRE_URLS")
    return [str(x).strip() for x in parsed if str(x).strip()]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def _base_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


def _extract_title_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "/list?" not in href or "title_no=" not in href:
            continue
        abs_url = urljoin(base_url, href)
        links.append(abs_url)
    # stable unique order
    seen = set()
    out = []
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _extract_episode_links(html: str, list_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "/viewer" not in href or "episode_no=" not in href:
            continue
        links.append(urljoin(list_url, href))
    seen = set()
    out = []
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _title_from_list_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    # /en/genre/title/list
    genre = _slug(parts[1] if len(parts) > 2 else "unknown")
    title_slug = _slug(parts[2] if len(parts) > 2 else "unknown")
    title_name = title_slug.replace("-", " ").title()
    return genre, title_slug, title_name


def _episode_from_url(url: str) -> dict:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    slug = _slug(parts[3] if len(parts) > 3 else "episode")
    qs = parse_qs(parsed.query)
    ep_no_raw = (qs.get("episode_no") or ["0"])[0]
    try:
        ep_no = int(ep_no_raw)
    except Exception:
        ep_no = 0
    return {"episode_no": ep_no, "episode_slug": slug, "viewer_url": url}


def _fetch_title_payload(
    list_url: str,
    timeout: int,
    max_episodes: int,
    headers: dict[str, str],
) -> dict:
    title_resp = requests.get(list_url, timeout=timeout, headers=headers)
    title_resp.raise_for_status()
    episode_links = _extract_episode_links(title_resp.text, list_url)
    episode_links = episode_links[: max(1, max_episodes)]
    genre, title_slug, title_name = _title_from_list_url(list_url)
    title_no = parse_qs(urlparse(list_url).query).get("title_no", [None])[0]
    episodes = [_episode_from_url(u) for u in episode_links]
    return {
        "genre": genre,
        "title_slug": title_slug,
        "title_name": title_name,
        "title_no": title_no,
        "list_url": list_url,
        "episodes": episodes,
    }


def crawl_webtoon_catalog() -> dict:
    logger.info("catalog_crawler start")
    sess = _session()
    headers = _base_headers()
    catalog = empty_catalog()
    genres: dict[str, dict] = {}
    timeout = max(5, int(settings.webtoon_catalog_request_timeout_sec))
    workers = max(1, int(settings.webtoon_catalog_workers))
    logger.info("catalog_crawler config timeout=%s workers=%s", timeout, workers)
    for genre_url in _genre_urls():
        logger.info("catalog_crawler genre_fetch url=%s", genre_url)
        resp = sess.get(genre_url, timeout=timeout)
        resp.raise_for_status()
        title_links = _extract_title_links(resp.text, genre_url)
        title_links = title_links[: max(1, settings.webtoon_catalog_max_titles_per_genre)]
        logger.info("catalog_crawler genre_titles url=%s count=%s", genre_url, len(title_links))
        done = 0
        with ThreadPoolExecutor(max_workers=min(workers, len(title_links) or 1)) as ex:
            futures = {
                ex.submit(
                    _fetch_title_payload,
                    list_url,
                    timeout,
                    settings.webtoon_catalog_max_episodes_per_title,
                    headers,
                ): list_url
                for list_url in title_links
            }
            for future in as_completed(futures):
                list_url = futures[future]
                done += 1
                try:
                    payload = future.result()
                    genre = payload["genre"]
                    if genre not in genres:
                        genres[genre] = {"genre": genre, "titles": []}
                    genres[genre]["titles"].append(payload)
                    logger.info(
                        "catalog_crawler title_done genre=%s title_slug=%s episodes=%s progress=%s/%s",
                        payload["genre"],
                        payload["title_slug"],
                        len(payload["episodes"]),
                        done,
                        len(title_links),
                    )
                except Exception as exc:
                    logger.info("catalog_crawler title_failed list_url=%s error=%s progress=%s/%s", list_url, exc, done, len(title_links))
                    continue
    catalog["genres"] = sorted(genres.values(), key=lambda g: g["genre"])
    saved = save_catalog(catalog)
    logger.info(
        "catalog_crawler done genres=%s titles=%s episodes=%s",
        saved.get("stats", {}).get("genre_count"),
        saved.get("stats", {}).get("title_count"),
        saved.get("stats", {}).get("episode_count"),
    )
    return saved

