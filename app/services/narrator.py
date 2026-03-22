from __future__ import annotations

from pathlib import Path

from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import SrtTimelineLine
from app.services.audio.audio_pipeline import run_audio_pipeline
from app.utils.errors import ProviderError


def generate_voice(
    srt_lines: list[SrtTimelineLine], panel_paths: list[str], audio_dir: Path
) -> tuple[Path, list[AudioSegmentSchema], list[dict], dict]:
    if not srt_lines:
        raise ProviderError("narrator", "elevenlabs", "Script is empty before TTS call", "TTS_EMPTY_SCRIPT")
    narration_path, segments, timeline, audio_meta = run_audio_pipeline(srt_lines, audio_dir, panel_paths=panel_paths)
    return narration_path, segments, timeline, audio_meta
