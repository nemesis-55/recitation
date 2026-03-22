from __future__ import annotations

from pathlib import Path

from app.utils.ffmpeg_runner import run_ffmpeg


def micro_pause_seconds(emotion: str, intensity: float) -> float:
    emo = (emotion or "neutral").lower()
    t = max(0.0, min(1.0, float(intensity)))
    if emo == "fear":
        return round(0.22 + (0.18 * t), 3)
    if emo == "sad":
        return round(0.2 + (0.16 * t), 3)
    if emo == "angry":
        return round(0.1 + (0.06 * (1.0 - t)), 3)
    return round(0.12 + (0.1 * t), 3)


def pause_seconds(emotion: str, intensity: float) -> float:
    emo = (emotion or "neutral").lower()
    base = {"angry": 0.2, "neutral": 0.3, "happy": 0.28, "sad": 0.8, "fear": 0.7}.get(emo, 0.3)
    if emo in {"angry", "happy"}:
        base = max(0.12, base - (0.1 * intensity))
    elif emo in {"sad", "fear"}:
        base = min(1.2, base + (0.2 * intensity))
    return round(base + micro_pause_seconds(emo, intensity), 3)


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
