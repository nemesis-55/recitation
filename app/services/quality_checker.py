from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import settings
from app.models.schemas import QualityReport
from app.utils.errors import ValidationError
from app.utils.ffmpeg_runner import probe_duration_seconds


def _stream_duration(stream: dict) -> float | None:
    raw = stream.get("duration")
    if raw in (None, "", "N/A"):
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _probe_streams(video_path: Path) -> dict:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(video_path),
    ]
    try:
        raw = subprocess.check_output(command, text=True)
        return json.loads(raw)
    except Exception as exc:
        raise ValidationError("quality_checker", f"ffprobe failed: {exc}", "FFPROBE_FAILED") from exc


def check_video(video_path: Path) -> QualityReport:
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise ValidationError("quality_checker", "Final video missing or empty", "EMPTY_VIDEO")

    duration = probe_duration_seconds(video_path)
    data = _probe_streams(video_path)
    streams = data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    video_duration = next((_stream_duration(s) for s in streams if s.get("codec_type") == "video" and _stream_duration(s) is not None), duration)
    audio_duration = next((_stream_duration(s) for s in streams if s.get("codec_type") == "audio" and _stream_duration(s) is not None), duration)
    av_delta_sec = abs(video_duration - audio_duration)

    duration_within_bounds = settings.min_video_duration_sec <= duration <= settings.max_video_duration_sec
    av_sync_within_bounds = av_delta_sec <= settings.av_sync_max_delta_sec
    checks = {
        "duration_within_bounds": duration_within_bounds,
        "av_sync_within_bounds": av_sync_within_bounds,
        "video_stream_present": has_video,
        "audio_stream_present": has_audio,
    }
    warnings = []
    if not duration_within_bounds:
        warnings.append(f"Duration out of bounds: {duration:.2f}s")
    if not av_sync_within_bounds:
        warnings.append(
            f"A/V delta exceeds threshold: delta={av_delta_sec:.3f}s threshold={settings.av_sync_max_delta_sec:.3f}s"
        )

    # Duration bounds are advisory; stream presence is mandatory.
    ok = checks["video_stream_present"] and checks["audio_stream_present"]
    if not ok:
        raise ValidationError("quality_checker", f"Video quality gates failed: {checks}", "QUALITY_GATE_FAILED")
    return QualityReport(
        ok=ok,
        duration_sec=duration,
        has_audio=has_audio,
        has_video=has_video,
        av_delta_sec=av_delta_sec,
        checks=checks,
        warnings=warnings,
    )
