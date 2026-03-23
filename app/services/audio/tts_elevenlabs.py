from __future__ import annotations

import time
from pathlib import Path

import requests

from app.config import settings
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError


def _normalize_accent(value: str | None) -> str:
    v = (value or "default").strip().lower().replace("-", "_")
    aliases = {
        "indian": "indian_english",
        "en_in": "indian_english",
        "enin": "indian_english",
        "india": "indian_english",
    }
    return aliases.get(v, v)


def _apply_humanize_voice_settings(base: dict[str, float | bool]) -> dict[str, float | bool]:
    if not getattr(settings, "elevenlabs_tts_humanize", True):
        return base
    out = dict(base)
    st = float(out.get("stability", 0.42))
    # ElevenLabs: higher stability = more monotone; nudge toward expressive band.
    if st >= 0.52:
        st = max(0.24, st - 0.12)
    elif st >= 0.40:
        st = max(0.22, st - 0.08)
    else:
        st = max(0.20, st - 0.04)
    out["stability"] = max(0.2, min(0.8, round(st, 3)))
    sb = float(out.get("similarity_boost", 0.78))
    out["similarity_boost"] = max(0.55, min(0.9, round(sb - 0.05, 3)))
    sy = float(out.get("style", 0.3))
    out["style"] = max(0.0, min(0.9, round(min(0.9, sy + 0.09), 3)))
    return out


def _apply_accent_preset(base: dict[str, float | bool]) -> dict[str, float | bool]:
    """Tune stability/style for clearer delivery; gentler when humanize is on (avoids robotic stiffness)."""
    accent = _normalize_accent(getattr(settings, "elevenlabs_tts_accent", None))
    if accent != "indian_english":
        return base
    out = dict(base)
    st = float(out.get("stability", 0.42))
    sb = float(out.get("similarity_boost", 0.78))
    sy = float(out.get("style", 0.3))
    if getattr(settings, "elevenlabs_tts_humanize", True):
        out["stability"] = max(0.2, min(0.8, round(st + 0.03, 3)))
        out["similarity_boost"] = max(0.55, min(0.9, round(sb + 0.03, 3)))
        out["style"] = max(0.0, min(0.9, round(sy * 0.95, 3)))
    else:
        out["stability"] = max(0.2, min(0.8, round(st + 0.06, 3)))
        out["similarity_boost"] = max(0.55, min(0.9, round(sb + 0.04, 3)))
        out["style"] = max(0.0, min(0.9, round(sy * 0.9, 3)))
    return out


def voice_settings_for_emotion(emotion: str, intensity: float, profile: dict | None = None) -> dict:
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
    elif emotion == "surprised":
        stability = 0.31
        style = 0.66 * intensity
    elif emotion == "curious":
        stability = 0.47
        style = 0.32 * intensity
    elif emotion == "confused":
        stability = 0.5
        style = 0.4 * intensity
    elif emotion == "determined":
        stability = 0.38
        style = 0.52 * intensity
    elif emotion == "hopeful":
        stability = 0.4
        style = 0.48 * intensity
    elif emotion == "resigned":
        stability = 0.58
        style = 0.28 * intensity
    elif emotion == "pain":
        stability = 0.33
        style = 0.62 * intensity
    elif emotion == "concerned":
        stability = 0.46
        style = 0.4 * intensity
    elif emotion == "worried":
        stability = 0.43
        style = 0.46 * intensity
    elif emotion == "weak":
        stability = 0.62
        style = 0.24 * intensity
    elif emotion == "urgent":
        stability = 0.3
        style = 0.68 * intensity
    elif emotion == "nostalgic":
        stability = 0.54
        style = 0.34 * intensity
    elif emotion == "reassuring":
        stability = 0.42
        style = 0.44 * intensity
    elif emotion == "regretful":
        stability = 0.56
        style = 0.36 * intensity
    elif emotion == "apologetic":
        stability = 0.5
        style = 0.38 * intensity
    elif emotion == "serious":
        stability = 0.44
        style = 0.42 * intensity
    elif emotion == "desperate":
        stability = 0.31
        style = 0.64 * intensity
    settings_out: dict[str, float | bool] = {
        "stability": max(0.2, min(0.8, round(stability, 3))),
        "similarity_boost": max(0.55, min(0.9, round(similarity, 3))),
        "style": max(0.0, min(0.9, round(style, 3))),
        "use_speaker_boost": True,
    }
    if profile:
        if "stability" in profile:
            settings_out["stability"] = max(0.2, min(0.8, round(float(profile["stability"]), 3)))
        if "similarity_boost" in profile:
            settings_out["similarity_boost"] = max(0.55, min(0.9, round(float(profile["similarity_boost"]), 3)))
        if "style" in profile:
            settings_out["style"] = max(0.0, min(0.9, round(float(profile["style"]), 3)))
        if "speed" in profile:
            settings_out["speed"] = max(0.7, min(1.2, round(float(profile["speed"]), 3)))
    if "speed" not in settings_out:
        settings_out["speed"] = max(
            0.7,
            min(1.2, float(getattr(settings, "elevenlabs_tts_speech_speed", 0.97))),
        )
    settings_out = _apply_humanize_voice_settings(settings_out)
    return _apply_accent_preset(settings_out)


def generate_tts(
    text: str,
    voice_id: str,
    emotion: str,
    intensity: float,
    output_path: Path,
    profile: dict | None = None,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> None:
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
    profile_sig = ""
    if profile:
        profile_sig = (
            f"|st={round(float(profile.get('stability', 0.0)),3)}"
            f"|sb={round(float(profile.get('similarity_boost', 0.0)),3)}"
            f"|sy={round(float(profile.get('style', 0.0)),3)}"
            f"|sp={round(float(profile.get('speed', 1.0)),3)}"
        )
    accent_sig = _normalize_accent(getattr(settings, "elevenlabs_tts_accent", None))
    humanize_sig = "h1" if getattr(settings, "elevenlabs_tts_humanize", True) else "h0"
    speed_sig = round(float(getattr(settings, "elevenlabs_tts_speech_speed", 0.97)), 3)
    ctx_sig = ""
    if previous_text or next_text:
        ctx_sig = (
            f"|prev={hash_text((previous_text or '')[:600])}|next={hash_text((next_text or '')[:600])}"
        )
    cache_key = hash_text(
        f"tts|{voice_id}|{emotion}|{round(float(intensity),3)}|{settings.elevenlabs_output_format}"
        f"|accent={accent_sig}|humanize={humanize_sig}|spd={speed_sig}{profile_sig}{ctx_sig}|{text.strip()}"
    )
    cached = read_cache_bytes("tts_audio", cache_key)
    if cached:
        output_path.write_bytes(cached)
        return

    query_params: dict[str, str | int] = {
        "output_format": settings.elevenlabs_output_format,
        "optimize_streaming_latency": int(getattr(settings, "elevenlabs_tts_optimize_streaming_latency", 0)),
    }

    for model_id in models:
        payload: dict[str, object] = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings_for_emotion(emotion, intensity, profile=profile),
        }
        if previous_text and str(previous_text).strip():
            payload["previous_text"] = str(previous_text)[:800]
        if next_text and str(next_text).strip():
            payload["next_text"] = str(next_text)[:800]
        for attempt in range(settings.provider_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    params=query_params,
                    timeout=settings.provider_timeout_sec,
                )
                if resp.status_code == 429 and attempt < settings.provider_retries:
                    time.sleep(0.9 * (2**attempt))
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
