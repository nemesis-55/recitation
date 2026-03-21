from __future__ import annotations

from pathlib import Path
from typing import List
from urllib.parse import urlparse, urlsplit, urlunsplit
import time

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup

from app.models.schemas import PanelAsset
from app.utils.errors import ValidationError


def is_webtoon_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    return parsed.scheme in {"http", "https"} and "webtoons.com" in host


def _extract_panel_urls(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []
    for img in soup.find_all("img", class_="_images"):
        url = img.get("data-url") or img.get("src")
        if url:
            urls.append(url)
    return urls


def _image_size(path: Path) -> tuple[int, int]:
    img = cv2.imread(str(path))
    if img is None:
        return 0, 0
    h, w = img.shape[:2]
    return w, h


def _validate_image_bytes(content: bytes) -> bool:
    if not content or len(content) < 128:
        return False
    arr = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img is not None


def _strip_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _download_with_fallback(session: requests.Session, panel_url: str, webtoon_url: str, timeout: int = 30) -> bytes:
    origin = f"{urlparse(webtoon_url).scheme}://{urlparse(webtoon_url).netloc}"
    image_headers = {
        "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0"),
        "Referer": webtoon_url,
        "Origin": origin,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    candidates = [panel_url]
    stripped = _strip_query(panel_url)
    if stripped != panel_url:
        candidates.append(stripped)

    last_exc: Exception | None = None
    for candidate in candidates:
        for attempt in range(3):
            try:
                resp = session.get(candidate, headers=image_headers, timeout=timeout)
                resp.raise_for_status()
                return resp.content
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
    raise last_exc if last_exc else RuntimeError("Unknown image download error")


def load_webtoon_panels(webtoon_url: str, panels_dir: Path) -> list[PanelAsset]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    try:
        res = session.get(webtoon_url, timeout=30)
        res.raise_for_status()
    except Exception as exc:
        raise ValidationError("webtoon_loader", f"Failed to fetch Webtoon page: {exc}", "WEBTOON_FETCH_FAILED") from exc

    panel_urls = _extract_panel_urls(res.text)
    if not panel_urls:
        raise ValidationError("webtoon_loader", "No panel images found in Webtoon HTML", "WEBTOON_NO_IMAGES")

    panels: list[PanelAsset] = []
    for i, panel_url in enumerate(panel_urls, start=1):
        out_path = panels_dir / f"webtoon_panel_{i:04d}.jpg"
        try:
            content = _download_with_fallback(session, panel_url, webtoon_url, timeout=30)
            if not _validate_image_bytes(content):
                raise ValueError("Downloaded content is not a valid image")
            out_path.write_bytes(content)
        except Exception as exc:
            raise ValidationError("webtoon_loader", f"Failed to download panel #{i}: {exc}", "WEBTOON_IMAGE_DOWNLOAD_FAILED") from exc

        w, h = _image_size(out_path)
        if w <= 0 or h <= 0:
            raise ValidationError(
                "webtoon_loader",
                f"Downloaded panel #{i} is unreadable at path: {out_path}",
                "WEBTOON_IMAGE_INVALID",
            )
        panels.append(
            PanelAsset(
                page_index=1,
                panel_index=i,
                image_path=str(out_path),
                bbox=(0, 0, w, h),
                confidence=1.0,
            )
        )
    return panels
