from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.utils.ffmpeg_runner import run_ffmpeg


def animate_panel(panel_image: str, duration: float, output_path: Path) -> Path:
    # Slow, stable Ken Burns motion for cinematic pacing.
    vf = (
        f"scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2,"
        "zoompan=z='min(zoom+0.0009,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={int(duration * settings.default_fps)}:s={settings.target_width}x{settings.target_height}:fps={settings.default_fps},"
        "format=yuv420p"
    )
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        panel_image,
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-r",
        str(settings.default_fps),
        str(output_path),
    ]
    run_ffmpeg(command, stage="panel_animator", timeout_sec=settings.stage_timeout_sec)
    return output_path
