from __future__ import annotations

from pathlib import Path

from app.utils.ffmpeg_runner import run_ffmpeg


def micro_pause_seconds(emotion: str, intensity: float) -> float:
    emo = (emotion or "neutral").lower()
    t = max(0.0, min(1.0, float(intensity)))
    if emo == "fear":
        return round(0.08 + (0.08 * t), 3)
    if emo == "surprised":
        return round(0.05 + (0.05 * t), 3)
    if emo == "sad":
        return round(0.07 + (0.09 * t), 3)
    if emo == "confused":
        return round(0.06 + (0.08 * t), 3)
    if emo in {"worried", "concerned", "apologetic", "frustrated", "defensive"}:
        return round(0.06 + (0.07 * t), 3)
    if emo == "urgent":
        return round(0.04 + (0.05 * (1.0 - t)), 3)
    if emo == "serious":
        return round(0.05 + (0.06 * t), 3)
    if emo in {"nostalgic", "regretful", "reassuring"}:
        return round(0.07 + (0.09 * t), 3)
    if emo in {"resigned", "weak"}:
        return round(0.08 + (0.1 * t), 3)
    if emo == "pain":
        return round(0.07 + (0.1 * t), 3)
    if emo == "desperate":
        return round(0.07 + (0.1 * t), 3)
    if emo == "angry":
        return round(0.04 + (0.04 * (1.0 - t)), 3)
    if emo == "teasing":
        return round(0.04 + (0.06 * t), 3)
    return round(0.05 + (0.06 * t), 3)


def pause_seconds(emotion: str, intensity: float) -> float:
    emo = (emotion or "neutral").lower()
    base = {
        "angry": 0.12,
        "neutral": 0.14,
        "happy": 0.12,
        "sad": 0.2,
        "fear": 0.22,
        "surprised": 0.13,
        "curious": 0.16,
        "confused": 0.19,
        "determined": 0.12,
        "hopeful": 0.13,
        "resigned": 0.22,
        "pain": 0.21,
        "concerned": 0.17,
        "worried": 0.2,
        "weak": 0.24,
        "urgent": 0.11,
        "nostalgic": 0.2,
        "reassuring": 0.14,
        "regretful": 0.21,
        "apologetic": 0.18,
        "serious": 0.13,
        "desperate": 0.21,
        "frustrated": 0.15,
        "teasing": 0.11,
        "defensive": 0.16,
    }.get(emo, 0.14)
    if emo in {"angry", "happy", "determined", "hopeful", "urgent", "serious", "teasing"}:
        base = max(0.08, base - (0.06 * intensity))
    elif emo in {
        "sad",
        "fear",
        "confused",
        "resigned",
        "pain",
        "concerned",
        "worried",
        "weak",
        "nostalgic",
        "regretful",
        "apologetic",
        "reassuring",
        "desperate",
        "frustrated",
        "defensive",
    }:
        base = min(0.4, base + (0.12 * intensity))
    elif emo == "surprised":
        base = min(0.26, max(0.1, base - (0.02 * intensity)))
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
