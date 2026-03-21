from __future__ import annotations

from pathlib import Path

from app.utils.ffmpeg_runner import run_ffmpeg


def pause_seconds(emotion: str, intensity: float) -> float:
    base = {"angry": 0.2, "neutral": 0.3, "happy": 0.28, "sad": 0.6, "fear": 0.8}.get(emotion, 0.3)
    if emotion in {"angry", "happy"}:
        base = max(0.12, base - (0.1 * intensity))
    elif emotion in {"sad", "fear"}:
        base = min(1.2, base + (0.2 * intensity))
    return round(base, 3)


def create_silence_clip(output_path: Path, duration_sec: float) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{max(0.05, duration_sec):.3f}",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(output_path),
        ],
        stage="pause_engine",
    )
