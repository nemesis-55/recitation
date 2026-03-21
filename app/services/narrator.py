from __future__ import annotations

import re
import time
from pathlib import Path

import requests
from openai import OpenAI
from pydub import AudioSegment

from app.config import settings
from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError


def _extract_binary_content(response: object) -> bytes:
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    read_fn = getattr(response, "read", None)
    if callable(read_fn):
        data = read_fn()
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
    raise RuntimeError("No binary audio content in provider response")


def _synthesize_line_openai(client: OpenAI, text: str, output_path: Path, voice: str | None = None) -> None:
    try:
        try:
            response = client.audio.speech.create(
                model=settings.openai_tts_model,
                voice=voice or settings.openai_tts_voice,
                input=text,
                response_format="mp3",
                timeout=settings.provider_timeout_sec,
            )
        except TypeError:
            # SDK compatibility fallback for versions without response_format support.
            response = client.audio.speech.create(
                model=settings.openai_tts_model,
                voice=voice or settings.openai_tts_voice,
                input=text,
                timeout=settings.provider_timeout_sec,
            )
        output_path.write_bytes(_extract_binary_content(response))
    except Exception as exc:
        raise ProviderError("narrator", "openai", f"OpenAI TTS failed: {exc}", "OPENAI_TTS_FAILED") from exc


def _synthesize_line_runway(text: str, output_path: Path) -> None:
    runway_tts_url = f"{settings.runway_api_base_url.rstrip('/')}/v1/audio/text-to-speech"
    headers = {
        "Authorization": f"Bearer {settings.runway_api_key}",
        "Content-Type": "application/json",
    }
    candidate_bodies = [
        {"text": text, "voice": "alloy", "format": "mp3", "sample_rate": 44100},
        {"text": text},
    ]
    last_exc: Exception | None = None
    for body in candidate_bodies:
        try:
            resp = requests.post(runway_tts_url, json=body, headers=headers, timeout=settings.provider_timeout_sec)
            resp.raise_for_status()

            # Runway may return either direct audio bytes or JSON containing audio URL/task payload.
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                data = resp.json()
                audio_url = data.get("audio_url") or data.get("url")
                if audio_url:
                    audio_resp = requests.get(audio_url, timeout=settings.provider_timeout_sec)
                    audio_resp.raise_for_status()
                    output_path.write_bytes(audio_resp.content)
                else:
                    raise ProviderError("narrator", "runway", f"Runway TTS JSON missing audio URL: {data}", "RUNWAY_TTS_INVALID_JSON")
            else:
                output_path.write_bytes(resp.content)
            return
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise ProviderError("narrator", "runway", f"Runway TTS failed: {last_exc}", "RUNWAY_TTS_FAILED") from last_exc


def _parse_emotion_voice_overrides(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in raw.split(","):
        token = item.strip()
        if not token or ":" not in token:
            continue
        key, value = token.split(":", 1)
        emotion = key.strip().lower()
        voice = value.strip()
        if emotion and voice:
            parsed[emotion] = voice
    return parsed


def _select_voice_for_line(line: ScriptLine, line_index: int) -> str:
    gender = (line.gender or "unknown").lower()
    emotion = (line.emotion or "neutral").lower()
    speaker = (line.speaker or "unknown_1").lower()
    if speaker == "narrator":
        return settings.openai_tts_voice_narrator
    # Keep dual-reciter style stable: unknown lines alternate male/female reciters.
    if gender == "unknown":
        return settings.openai_tts_voice_male if line_index % 2 == 0 else settings.openai_tts_voice_female
    overrides = _parse_emotion_voice_overrides(settings.openai_tts_emotion_overrides)
    if emotion in overrides and gender in {"male", "female"}:
        return overrides[emotion]
    if gender == "female":
        return settings.openai_tts_voice_female
    if gender == "male":
        return settings.openai_tts_voice_male
    return settings.openai_tts_voice_unknown


def _normalize_tts_text(text: str, emotion: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return cleaned
    lowered = cleaned.lower()
    if re.match(r"^h+u+\.{0,3}$", lowered) or re.match(r"^h+a+\.{0,3}$", lowered):
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    if emotion == "fear" and "..." not in cleaned:
        cleaned = cleaned.replace(".", "...", 1)
    return cleaned


def _tts_cache_key_for_line(text: str, line: ScriptLine, selected_voice: str) -> str:
    return hash_text(
        f"{settings.openai_tts_model}|{selected_voice}|{line.gender}|{line.emotion}|{settings.tts_provider}|{text.strip().lower()}"
    )


def _synthesize_line_with_clients(
    text: str,
    output_path: Path,
    openai_client: OpenAI | None,
    selected_voice: str,
) -> None:
    provider = (settings.tts_provider or "auto").lower()
    openai_allowed = provider in {"auto", "openai"} and bool(settings.openai_api_key)
    runway_allowed = provider in {"auto", "runway"} and bool(settings.runway_api_key)

    errors: list[str] = []
    if openai_allowed:
        try:
            client = openai_client or OpenAI(api_key=settings.openai_api_key, max_retries=0)
            _synthesize_line_openai(client, text, output_path, voice=selected_voice)
            return
        except ProviderError as exc:
            errors.append(str(exc))
            if provider == "openai":
                raise
    if runway_allowed:
        try:
            _synthesize_line_runway(text, output_path)
            return
        except ProviderError as exc:
            errors.append(str(exc))
            if provider == "runway":
                raise
    detail = "; ".join(errors) if errors else "No TTS provider available (check TTS_PROVIDER and provider API keys)"
    raise ProviderError("narrator", "tts", detail, "TTS_PROVIDER_FAILED")


def generate_voice(script: list[ScriptLine], audio_dir: Path) -> tuple[Path, list[AudioSegmentSchema]]:
    if not script:
        raise ProviderError("narrator", "tts", "Script is empty before TTS call", "TTS_EMPTY_SCRIPT")

    segments: list[AudioSegmentSchema] = []
    merged = AudioSegment.silent(duration=0)
    cursor_sec = 0.0
    openai_client = OpenAI(api_key=settings.openai_api_key, max_retries=0) if settings.openai_api_key else None

    pause_ms = 250
    for idx, line in enumerate(script):
        if line.gender == "unknown":
            # Enforce two-reciter output even when speaker inference is uncertain.
            line.gender = "male" if idx % 2 == 0 else "female"
        selected_voice = _select_voice_for_line(line, idx)
        line.voice = selected_voice
        text = _normalize_tts_text(line.narration.strip(), line.emotion.lower())
        line_path = audio_dir / f"line_{idx:03d}.mp3"
        if not text:
            # Keep timeline/audio sync for textless or filler-suppressed panels by
            # inserting an explicit silence segment instead of skipping the line.
            silence_ms = max(250, int(settings.min_panel_duration_sec * 1000))
            silent_clip = AudioSegment.silent(duration=silence_ms)
            silent_clip.export(line_path, format="mp3")
            duration_sec = silence_ms / 1000.0
            start = cursor_sec
            end = start + duration_sec
            segments.append(
                AudioSegmentSchema(
                    line_index=idx,
                    audio_path=str(line_path),
                    start_sec=start,
                    end_sec=end,
                    duration_sec=duration_sec,
                )
            )
            merged += silent_clip
            cursor_sec = len(merged) / 1000.0
            continue
        cache_key = _tts_cache_key_for_line(text=text, line=line, selected_voice=selected_voice)
        cached_audio = read_cache_bytes("tts_audio", cache_key)
        if cached_audio:
            line_path.write_bytes(cached_audio)
        else:
            last_error = None
            for attempt in range(settings.provider_retries + 1):
                try:
                    _synthesize_line_with_clients(
                        text,
                        line_path,
                        openai_client=openai_client,
                        selected_voice=selected_voice,
                    )
                    write_cache_bytes("tts_audio", cache_key, line_path.read_bytes())
                    last_error = None
                    break
                except ProviderError as exc:
                    last_error = exc
                    if attempt >= settings.provider_retries:
                        raise
                    time.sleep(0.6 * (attempt + 1))
            if last_error:
                raise last_error

        clip = AudioSegment.from_file(line_path)
        # Keep segment duration aligned with merged narration timeline,
        # including the inter-line pause that is appended right after the clip.
        duration_sec = (len(clip) + pause_ms) / 1000.0
        start = cursor_sec
        end = start + duration_sec
        segments.append(
            AudioSegmentSchema(
                line_index=idx,
                audio_path=str(line_path),
                start_sec=start,
                end_sec=end,
                duration_sec=duration_sec,
            )
        )
        merged += clip + AudioSegment.silent(duration=pause_ms)
        cursor_sec = (len(merged) / 1000.0)

    narration_path = audio_dir / "narration.mp3"
    merged.export(narration_path, format="mp3")
    return narration_path, segments
