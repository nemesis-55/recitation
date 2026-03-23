#!/usr/bin/env python3
"""
Rebuild the YouTube landscape video from an existing pipeline run folder (no OCR/TTS).

Uses ``meta/timeline.json`` for panel paths, durations, and ``youtube_motion`` presets,
re-renders panel clips with the **current** ``panel_animator`` settings (e.g. blur / transparent pad),
then concat + mux like the main pipeline.

Usage (from ``manga_video_pipeline/``)::

    python scripts/rebuild_youtube_from_run.py \\
      --run-dir outputs/runs/action/a-flame-reborn/episode-1

    # Quick test: first 3 panels only → ``final/video_youtube_rebuild.mp4``
    python scripts/rebuild_youtube_from_run.py --run-dir /path/to/episode-1 --max-panels 3

    # Custom output name under ``final/``
    python scripts/rebuild_youtube_from_run.py --run-dir ... --output-name video_youtube_test.mp4

Requires:
  - ``meta/timeline.json``
  - Panel images (paths in timeline, or ``panels/webtoon_panel_*.jpg`` under run-dir)
  - ``audio/narration.mp3`` (or pass ``--narration``); optional ``final/subtitles.srt``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings  # noqa: E402
from app.services.panel_animator import animate_panel  # noqa: E402
from app.services.video_editor import assemble_video  # noqa: E402


def _load_timeline(run_dir: Path) -> list[dict]:
    path = run_dir / "meta" / "timeline.json"
    if not path.is_file():
        raise SystemExit(f"Missing timeline: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("timeline.json must be a JSON array")
    return data


def _resolve_panel(run_dir: Path, raw: str) -> Path:
    p = Path(raw)
    if p.is_file():
        return p.resolve()
    cand = run_dir / "panels" / p.name
    if cand.is_file():
        return cand.resolve()
    raise FileNotFoundError(f"Panel not found: {raw} (tried {cand})")


def _find_narration(run_dir: Path, override: Path | None) -> Path:
    if override is not None:
        if not override.is_file():
            raise SystemExit(f"--narration not found: {override}")
        return override.resolve()
    for rel in ("audio/narration.mp3", "narration.mp3"):
        p = run_dir / rel
        if p.is_file():
            return p.resolve()
    raise SystemExit(
        f"No narration MP3 under {run_dir} (expected audio/narration.mp3). "
        "Pass --narration /path/to/narration.mp3"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild YouTube video from run outputs + timeline.json")
    ap.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Episode run folder (contains meta/timeline.json, panels/, etc.)",
    )
    ap.add_argument(
        "--max-panels",
        type=int,
        default=0,
        help="If > 0, only rebuild the first N timeline entries (quick test).",
    )
    ap.add_argument(
        "--clips-subdir",
        type=str,
        default="rebuild_clips",
        help="Subfolder under run-dir/clips/ for new segments (default: rebuild_clips).",
    )
    ap.add_argument(
        "--output-name",
        type=str,
        default="video_youtube_rebuild.mp4",
        help="Filename under run-dir/final/ (default: video_youtube_rebuild.mp4)",
    )
    ap.add_argument("--narration", type=Path, default=None, help="Override path to narration MP3")
    ap.add_argument(
        "--subtitles",
        type=Path,
        default=None,
        help="SRT path (default: run-dir/final/subtitles.srt if present)",
    )
    ap.add_argument(
        "--no-subs",
        action="store_true",
        help="Do not mux subtitles even if subtitles.srt exists",
    )
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")

    entries = _load_timeline(run_dir)
    if args.max_panels and args.max_panels > 0:
        entries = entries[: int(args.max_panels)]

    clips_dir = run_dir / "clips" / str(args.clips_subdir).strip().replace("..", "")
    clips_dir.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    for i, row in enumerate(entries, start=1):
        raw_panel = str(row.get("panel_path") or "").strip()
        if not raw_panel:
            raise SystemExit(f"timeline entry {i} missing panel_path")
        panel = _resolve_panel(run_dir, raw_panel)
        dur = float(row.get("duration_sec") or 2.0)
        dur = max(0.05, min(120.0, dur))
        motion = (row.get("youtube_motion") or "center_zoom_out").strip()
        out_clip = clips_dir / f"clip_yt_{i:03d}.mp4"
        print(f"[{i}/{len(entries)}] {panel.name}  {dur:.2f}s  motion={motion}", flush=True)
        animate_panel(str(panel), dur, out_clip, profile="youtube", youtube_motion=motion)
        clips.append(out_clip)

    narration = _find_narration(run_dir, args.narration)
    final_dir = run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    out_video = final_dir / args.output_name

    sub_path: Path | None = None
    if not args.no_subs:
        if args.subtitles is not None:
            sub_path = args.subtitles if args.subtitles.is_file() else None
        else:
            cand = final_dir / "subtitles.srt"
            sub_path = cand if cand.is_file() else None

    assemble_video(
        clips=clips,
        narration_path=narration,
        output_path=out_video,
        subtitles_path=sub_path,
        bgm_path=None,
        playback_speed=settings.video_playback_speed,
        profile="youtube",
        youtube_clips_preformatted=True,
    )
    print(f"Wrote {out_video}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
