from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image at {path}")
    return img


def save_crop(image: np.ndarray, bbox: tuple[int, int, int, int], out_path: Path) -> None:
    x, y, w, h = bbox
    crop = image[y : y + h, x : x + w]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop)


def sort_boxes_reading_order(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    return sorted(boxes, key=lambda b: (b[1] // 60, b[0]))
