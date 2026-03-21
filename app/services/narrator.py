from __future__ import annotations

from pathlib import Path

from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine
from app.services.audio.audio_pipeline import run_audio_pipeline
from app.services.audio.character_engine import get_voice as _select_elevenlabs_voice
from app.services.audio.dialogue_analyzer import estimate_emotion_intensity as _estimate_emotion_intensity
from app.services.audio.pause_engine import pause_seconds as _pause_seconds_for_line
from app.services.audio.speech_renderer import render_speech as _render_performance_text
from app.utils.cache_utils import hash_text
from app.utils.errors import ProviderError


def _tts_cache_key_for_line(text: str, line: ScriptLine, selected_voice: str, provider: str) -> str:
    return hash_text(f"{provider}|{selected_voice}|{line.gender}|{line.emotion}|{text.strip().lower()}")


def generate_voice(script: list[ScriptLine], audio_dir: Path) -> tuple[Path, list[AudioSegmentSchema], dict]:
    if not script:
        raise ProviderError("narrator", "elevenlabs", "Script is empty before TTS call", "TTS_EMPTY_SCRIPT")
    narration_path, segments, _timeline, audio_meta = run_audio_pipeline(script, audio_dir)
    return narration_path, segments, audio_meta
