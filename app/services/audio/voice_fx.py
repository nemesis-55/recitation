from __future__ import annotations

from pathlib import Path

from app.utils.ffmpeg_runner import run_ffmpeg


def apply_voice_fx(input_path: Path, output_path: Path, gender: str, emotion: str, intensity: float) -> None:
    pitch_factor = 1.0
    if gender == "female":
        pitch_factor = 1.045
    elif gender == "male":
        pitch_factor = 0.985
    if emotion == "fear":
        pitch_factor *= 1.02
    elif emotion == "sad":
        pitch_factor *= 0.99
    atempo = max(0.92, min(1.06, 1.0 + ((0.5 - intensity) * 0.08)))
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-af",
            f"asetrate=44100*{pitch_factor:.5f},aresample=44100,atempo={atempo:.4f}",
            str(output_path),
        ],
        stage="voice_fx",
    )
