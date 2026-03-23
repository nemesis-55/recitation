#!/usr/bin/env python3
"""
Render short demo clips to preview panel motion (zoom in → zoom out + pan).

Usage (from ``manga_video_pipeline/``)::

    python scripts/render_ken_burns_sample.py
    python scripts/render_ken_burns_sample.py --panel /path/to/panel.jpg --duration 2.5

Outputs under ``outputs/samples/``:
  - ``sample_youtube_ken_burns.mp4`` — 1920×1080
  - ``sample_reel_ken_burns.mp4`` — 1080×1920
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.panel_animator import animate_panel  # noqa: E402


def _default_panel() -> Path | None:
    """Pick a known panel from repo outputs if present."""
    candidates = [
        _ROOT
        / "outputs"
        / "runs"
        / "horror"
        / "apocalypse-live"
        / "episode-1"
        / "panels"
        / "webtoon_panel_0001.jpg",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Ken Burns sample clips (YouTube + Reel).")
    ap.add_argument(
        "--panel",
        type=Path,
        default=None,
        help="Panel image (JPEG/PNG). Default: first available run panel under outputs/runs.",
    )
    ap.add_argument("--duration", type=float, default=2.0, help="Clip length in seconds (default 2).")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "outputs" / "samples",
        help="Output directory (default: outputs/samples/).",
    )
    args = ap.parse_args()

    panel = args.panel
    if panel is None:
        panel = _default_panel()
    if panel is None or not panel.is_file():
        print(
            "No panel image found. Pass --panel /path/to/panel.jpg\n"
            "Or generate a run first so outputs/runs/.../panels/*.jpg exists.",
            file=sys.stderr,
        )
        return 1

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = max(0.5, min(30.0, float(args.duration)))

    yt = out_dir / "sample_youtube_ken_burns.mp4"
    reel = out_dir / "sample_reel_ken_burns.mp4"

    print(f"Panel: {panel}")
    print(f"Duration: {dur}s")
    animate_panel(str(panel), dur, yt, profile="youtube")
    animate_panel(str(panel), dur, reel, profile="reel")
    print(f"Wrote: {yt}")
    print(f"Wrote: {reel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
