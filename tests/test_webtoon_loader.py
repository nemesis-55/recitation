from pathlib import Path

import cv2
import numpy as np

from app.models.schemas import PanelAsset
from app.routes.generate import _validate_panel_assets
from app.services.webtoon_loader import _validate_image_bytes


def test_validate_image_bytes_rejects_non_image():
    assert _validate_image_bytes(b"not an image payload") is False


def test_validate_image_bytes_accepts_jpeg():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", img)
    assert ok is True
    assert _validate_image_bytes(encoded.tobytes()) is True


def test_validate_panel_assets_reports_missing_and_unreadable(tmp_path: Path):
    existing = tmp_path / "ok.jpg"
    existing.write_bytes(b"\x00\x01")
    unreadable = tmp_path / "empty.jpg"
    unreadable.write_bytes(b"")
    missing = tmp_path / "missing.jpg"
    panels = [
        PanelAsset(page_index=1, panel_index=1, image_path=str(existing), bbox=(0, 0, 1, 1)),
        PanelAsset(page_index=1, panel_index=2, image_path=str(unreadable), bbox=(0, 0, 1, 1)),
        PanelAsset(page_index=1, panel_index=3, image_path=str(missing), bbox=(0, 0, 1, 1)),
    ]
    qa = _validate_panel_assets(panels)
    assert qa["count"] == 3
    assert qa["missing_count"] == 1
    assert qa["unreadable_count"] == 1
from app.services.webtoon_loader import _extract_panel_urls, is_webtoon_url


def test_is_webtoon_url():
    assert is_webtoon_url("https://www.webtoons.com/en/action/foo/list?title_no=1")
    assert not is_webtoon_url("https://example.com/chapter/1")


def test_extract_panel_urls_prefers_data_url():
    html = """
    <html><body>
      <img class="_images" data-url="https://img.cdn/panel_0001.jpg" src="https://compressed/p1.jpg"/>
      <img class="_images" src="https://img.cdn/panel_0002.jpg"/>
      <img class="other" src="https://img.cdn/ignored.jpg"/>
    </body></html>
    """
    urls = _extract_panel_urls(html)
    assert urls == ["https://img.cdn/panel_0001.jpg", "https://img.cdn/panel_0002.jpg"]
