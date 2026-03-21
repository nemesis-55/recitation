from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from app.config import settings
from app.utils.errors import PipelineError


def run_ffmpeg(command: list[str], stage: str, timeout_sec: int = 300) -> None:
    last_error = None
    for attempt in range(settings.provider_retries + 1):
        try:
            subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                check=True,
                text=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = PipelineError(stage=stage, message=exc.stderr[-1000:], error_code="FFMPEG_FAILED")
        except subprocess.TimeoutExpired as exc:
            cmd = " ".join(shlex.quote(item) for item in command)
            last_error = PipelineError(stage=stage, message=f"FFmpeg timeout: {cmd}", error_code="FFMPEG_TIMEOUT")
        if attempt < settings.provider_retries:
            time.sleep(0.6 * (attempt + 1))
    if last_error:
        raise last_error


def probe_duration_seconds(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(command, text=True).strip()
        return float(out)
    except Exception as exc:
        raise PipelineError("quality_checker", f"Unable to probe duration for {path}: {exc}", "FFPROBE_ERROR") from exc
