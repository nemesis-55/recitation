from __future__ import annotations

from pathlib import Path

import cv2

from app.models.schemas import PageAsset, PanelAsset
from app.utils.image_utils import read_image, save_crop, sort_boxes_reading_order


def _detect_panel_boxes(image) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = image.shape[:2]
    min_area = (w * h) * 0.03
    boxes: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area < min_area:
            continue
        if bw < w * 0.15 or bh < h * 0.15:
            continue
        boxes.append((x, y, bw, bh))
    return sort_boxes_reading_order(boxes)


def _fallback_grid(image) -> list[tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    return [
        (0, 0, w // 2, h // 2),
        (w // 2, 0, w - w // 2, h // 2),
        (0, h // 2, w // 2, h - h // 2),
        (w // 2, h // 2, w - w // 2, h - h // 2),
    ]


def extract_panels(page: PageAsset, panels_dir: Path) -> list[PanelAsset]:
    image = read_image(Path(page.image_path))
    boxes = _detect_panel_boxes(image)
    if len(boxes) < 2:
        boxes = _fallback_grid(image)

    panels: list[PanelAsset] = []
    for idx, box in enumerate(boxes, start=1):
        out_path = panels_dir / f"page_{page.page_index:03d}_panel_{idx:03d}.png"
        save_crop(image, box, out_path)
        confidence = 0.8 if len(boxes) >= 2 else 0.3
        panels.append(
            PanelAsset(
                page_index=page.page_index,
                panel_index=idx,
                image_path=str(out_path),
                bbox=box,
                confidence=confidence,
            )
        )
    return panels
