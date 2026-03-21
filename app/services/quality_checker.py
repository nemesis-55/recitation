from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import settings
from app.models.schemas import QualityReport
from app.utils.errors import ValidationError
from app.utils.ffmpeg_runner import probe_duration_seconds


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

    duration_within_bounds = settings.min_video_duration_sec <= duration <= settings.max_video_duration_sec
    checks = {
        "duration_within_bounds": duration_within_bounds,
        "video_stream_present": has_video,
        "audio_stream_present": has_audio,
    }
    warnings = []
    if not duration_within_bounds:
        warnings.append(f"Duration out of bounds: {duration:.2f}s")

    # Duration bounds are advisory; stream presence is mandatory.
    ok = checks["video_stream_present"] and checks["audio_stream_present"]
    if not ok:
        raise ValidationError("quality_checker", f"Video quality gates failed: {checks}", "QUALITY_GATE_FAILED")
    return QualityReport(ok=ok, duration_sec=duration, has_audio=has_audio, has_video=has_video, checks=checks, warnings=warnings)
