from __future__ import annotations

import random
import time
from pathlib import Path

import requests

from app.config import settings
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError


def voice_settings_for_emotion(emotion: str, intensity: float) -> dict:
    stability = 0.42
    similarity = 0.78
    style = 0.3
    if emotion == "angry":
        stability = 0.28
        style = 0.72 * intensity
    elif emotion == "fear":
        stability = 0.3
        style = 0.62 * intensity
    elif emotion == "sad":
        stability = 0.56
        style = 0.36 * intensity
    elif emotion == "happy":
        stability = 0.34
        style = 0.58 * intensity
    return {
        "stability": max(0.2, min(0.8, round(stability, 3))),
        "similarity_boost": max(0.55, min(0.9, round(similarity, 3))),
        "style": max(0.0, min(0.9, round(style, 3))),
        "use_speaker_boost": True,
    }


def generate_tts(text: str, voice_id: str, emotion: str, intensity: float, output_path: Path) -> None:
    headers = {
        "xi-api-key": str(settings.elevenlabs_api_key),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    url = f"{settings.elevenlabs_api_base_url.rstrip('/')}/v1/text-to-speech/{voice_id}"
    models = [settings.elevenlabs_tts_model]
    fallback = (settings.elevenlabs_tts_model_fallback or "").strip()
    if fallback and fallback not in models:
        models.append(fallback)
    cache_key = hash_text(
        f"tts|{voice_id}|{emotion}|{round(float(intensity),3)}|{settings.elevenlabs_output_format}|{text.strip()}"
    )
    cached = read_cache_bytes("tts_audio", cache_key)
    if cached:
        output_path.write_bytes(cached)
        return

    for model_id in models:
        payload = {
            "text": text,
            "model_id": model_id,
            "output_format": settings.elevenlabs_output_format,
            "voice_settings": voice_settings_for_emotion(emotion, intensity),
        }
        for attempt in range(settings.provider_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=settings.provider_timeout_sec)
                if resp.status_code == 429 and attempt < settings.provider_retries:
                    time.sleep(0.9 * (2**attempt) + random.uniform(0.0, 0.3))
                    continue
                if resp.status_code == 402:
                    raise ProviderError(
                        "narrator",
                        "elevenlabs",
                        "ElevenLabs credits/quota exhausted (402 Payment Required).",
                        "ELEVENLABS_CREDITS_EXHAUSTED",
                    )
                if resp.status_code == 401:
                    raise ProviderError(
                        "narrator",
                        "elevenlabs",
                        "ElevenLabs unauthorized. Check API key permissions for text_to_speech.",
                        "ELEVENLABS_MISSING_TTS_PERMISSION",
                    )
                if resp.status_code in {400, 422} and model_id != models[-1]:
                    break
                resp.raise_for_status()
                output_path.write_bytes(resp.content)
                write_cache_bytes("tts_audio", cache_key, resp.content)
                return
            except ProviderError:
                raise
            except Exception as exc:
                if attempt >= settings.provider_retries:
                    raise ProviderError("narrator", "elevenlabs", f"ElevenLabs TTS failed: {exc}", "ELEVENLABS_TTS_FAILED") from exc
                time.sleep(0.6 * (attempt + 1))
    raise ProviderError("narrator", "elevenlabs", "ElevenLabs TTS failed for all models", "ELEVENLABS_TTS_FAILED")
