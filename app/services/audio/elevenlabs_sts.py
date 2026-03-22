from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from app.config import settings
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError


def convert_speech_to_voice(input_audio: Path, voice_id: str, output_audio: Path) -> None:
    if not settings.elevenlabs_sts_enabled:
        output_audio.write_bytes(input_audio.read_bytes())
        return
    if not input_audio.exists():
        raise ProviderError("voice_changer", "elevenlabs", f"STS input not found: {input_audio}", "ELEVENLABS_STS_INPUT_MISSING")
    cache_key = hash_text(
        f"sts|{voice_id}|{settings.elevenlabs_sts_model_id}|{settings.elevenlabs_output_format}|"
        f"{settings.elevenlabs_sts_remove_background_noise}|{input_audio.stat().st_size}"
    )
    cached = read_cache_bytes("elevenlabs_sts", cache_key)
    if cached:
        output_audio.write_bytes(cached)
        return

    url = f"{settings.elevenlabs_api_base_url.rstrip('/')}/v1/speech-to-speech/{voice_id}?output_format={settings.elevenlabs_output_format}"
    headers = {"xi-api-key": str(settings.elevenlabs_api_key)}
    form = {
        "model_id": settings.elevenlabs_sts_model_id,
        "voice_settings": json.dumps({"stability": 0.38, "similarity_boost": 0.8}),
        "remove_background_noise": str(bool(settings.elevenlabs_sts_remove_background_noise)).lower(),
    }
    for attempt in range(settings.provider_retries + 1):
        try:
            with input_audio.open("rb") as f:
                files = {"audio": (input_audio.name, f, "audio/mpeg")}
                resp = requests.post(url, headers=headers, data=form, files=files, timeout=max(settings.provider_timeout_sec, 90))
            if resp.status_code == 429 and attempt < settings.provider_retries:
                time.sleep(0.9 * (2**attempt))
                continue
            resp.raise_for_status()
            output_audio.write_bytes(resp.content)
            write_cache_bytes("elevenlabs_sts", cache_key, resp.content)
            return
        except Exception as exc:
            if attempt >= settings.provider_retries:
                raise ProviderError("voice_changer", "elevenlabs", f"ElevenLabs STS failed: {exc}", "ELEVENLABS_STS_FAILED") from exc
            time.sleep(0.5 * (attempt + 1))

