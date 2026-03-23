from __future__ import annotations
import re
import time
from pathlib import Path

import requests

from app.config import settings
from app.models.schemas import ScriptLine
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError


def _event_prompt_map() -> dict[str, list[str]]:
    return {
        "impact": [
            "Heavy cinematic punch impact, body hit, deep low-end thump, tight transient",
            "Close-up impact hit with short bass thud and cloth rustle",
        ],
        "thump": [
            "Body fall impact on hard floor, cloth movement, dull cinematic thump",
            "Weighty drop impact with low thump and room tail",
        ],
        "movement": [
            "Fast cloth swoosh and sudden movement pass-by",
            "Airy whoosh movement with light cloth detail",
        ],
        "light_breath": [
            "Subtle nervous breath, short inhale and light exhale, close mic",
        ],
        "heavy_breath": [
            "Heavy breath under stress, controlled but intense inhale/exhale",
        ],
    }


def detect_events(text: str, emotion: str, intensity: float) -> list[str]:
    out: list[str] = []
    lowered = (text or "").lower()
    if re.search(r"\b(hit|punch|slam|smash|strike|attack)\b", lowered):
        out.append("impact")
    if re.search(r"\b(fall|fell|drop|crash|land)\b", lowered):
        out.append("thump")
    if re.search(r"\b(run|rush|dash|move|movement|whoosh|swoosh|slash)\b", lowered):
        out.append("movement")
    if (emotion or "").lower() == "fear":
        out.append("light_breath")
    if float(intensity) >= 0.7:
        out.append("heavy_breath")
    # preserve order but unique
    dedup: list[str] = []
    for evt in out:
        if evt not in dedup:
            dedup.append(evt)
    return dedup


def _event_from_line(line: ScriptLine) -> str | None:
    text = (line.narration or "").lower()
    if re.search(r"\b(hit|punch|slam|smash|strike)\b", text):
        return "impact"
    if re.search(r"\b(fall|fell|drop|crash)\b", text):
        return "thump"
    if re.search(r"\b(run|rush|dash|move|movement|whoosh)\b", text):
        return "movement"
    if (line.emotion or "").lower() == "fear" or re.search(r"\b(hu+|ha+|ah+|uh+|gasp)\b", text):
        return "light_breath"
    return None


def _duration_for_intensity(intensity: float) -> float:
    return max(0.5, min(4.0, round(0.55 + (float(intensity) * 1.7), 2)))


def generate_sfx_to_file(prompt: str, duration_seconds: float, output_path: Path) -> None:
    if not settings.elevenlabs_sfx_enabled:
        raise ProviderError("sfx_engine", "elevenlabs", "ELEVENLABS_SFX_ENABLED is false", "ELEVENLABS_SFX_DISABLED")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_duration = max(0.5, min(30.0, float(duration_seconds)))
    safe_influence = max(0.0, min(1.0, float(settings.elevenlabs_sfx_prompt_influence)))
    cache_key = hash_text(
        f"sfx_runtime|{prompt.strip()}|{safe_duration:.3f}|{settings.elevenlabs_sfx_model_id}|"
        f"{settings.elevenlabs_sfx_output_format}|{safe_influence:.3f}"
    )
    cached = read_cache_bytes("elevenlabs_sfx", cache_key)
    if cached:
        output_path.write_bytes(cached)
        return
    headers = {
        "xi-api-key": str(settings.elevenlabs_api_key),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    url = f"{settings.elevenlabs_api_base_url.rstrip('/')}/v1/sound-generation?output_format={settings.elevenlabs_sfx_output_format}"
    payload = {
        "text": prompt,
        "duration_seconds": safe_duration,
        "prompt_influence": safe_influence,
        "model_id": settings.elevenlabs_sfx_model_id,
    }
    for attempt in range(settings.provider_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.provider_timeout_sec)
            if resp.status_code == 429 and attempt < settings.provider_retries:
                time.sleep(0.9 * (2**attempt))
                continue
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            write_cache_bytes("elevenlabs_sfx", cache_key, resp.content)
            return
        except Exception as exc:
            if attempt >= settings.provider_retries:
                raise ProviderError(
                    "sfx_engine",
                    "elevenlabs",
                    f"ElevenLabs sound-generation failed: {exc}",
                    "ELEVENLABS_SFX_FAILED",
                ) from exc
            time.sleep(0.5 * (attempt + 1))


def materialize_sfx_for_line(line: ScriptLine, work_dir: Path, line_index: int) -> Path | None:
    event = _event_from_line(line)
    if not event:
        return None
    prompt = _event_prompt_map()[event][0]
    intensity = float(line.emotion_intensity if line.emotion_intensity is not None else 0.5)
    duration = _duration_for_intensity(intensity)
    cache_key = hash_text(
        f"sfx|{event}|{prompt}|{duration}|{settings.elevenlabs_sfx_model_id}|{settings.elevenlabs_sfx_output_format}"
    )
    cached = read_cache_bytes("elevenlabs_sfx", cache_key)
    out = work_dir / f"sfx_{line_index:03d}_{event}.mp3"
    if cached:
        out.write_bytes(cached)
        return out
    generate_sfx_to_file(prompt, duration, out)
    write_cache_bytes("elevenlabs_sfx", cache_key, out.read_bytes())
    return out


def pick_sfx(line: ScriptLine, sfx_root: Path) -> list[Path]:
    # Backward-compatible helper retained for tests/callers; no local fallback policy.
    _ = sfx_root
    event = _event_from_line(line)
    if not event:
        return []
    return [Path(f"event:/{event}")]
