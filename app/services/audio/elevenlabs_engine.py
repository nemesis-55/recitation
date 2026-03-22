from __future__ import annotations

from pathlib import Path

from app.services.audio.music_engine import generate_scene_music
from app.services.audio.sfx_engine import generate_sfx_to_file
from app.services.audio.tts_elevenlabs import generate_tts


def generate_voice_line(
    text: str,
    voice_id: str,
    emotion: str,
    intensity: float,
    output_path: Path,
    voice_settings: dict | None = None,
) -> Path:
    generate_tts(
        text=text,
        voice_id=voice_id,
        emotion=emotion,
        intensity=float(intensity),
        output_path=output_path,
        profile=voice_settings or {},
    )
    return output_path


def generate_sfx_event(event_prompt: str, duration_sec: float, output_path: Path) -> Path:
    generate_sfx_to_file(prompt=event_prompt, duration_seconds=duration_sec, output_path=output_path)
    return output_path


def generate_scene_music_track(prompt: str, duration_ms: int, output_path: Path) -> Path:
    generate_scene_music(prompt=prompt, duration_ms=duration_ms, output_path=output_path)
    return output_path

