"""
Scene-level music generation via ElevenLabs Music API (fatal on provider failure).
"""
from __future__ import annotations

import email
import json
import shutil
import time
from collections import Counter
from pathlib import Path

import requests

from app.config import settings
from app.models.schemas import ScriptLine
from app.services.audio.pause_engine import pause_seconds
from app.utils.cache_utils import hash_text, read_cache_bytes, write_cache_bytes
from app.utils.errors import ProviderError

from app.services.audio.bgm_library import materialize_bed_for_scene, pick_bgm_slot


def _dominant_emotion(lines: list[ScriptLine]) -> str:
    emotions = [(line.emotion or "neutral").lower() for line in lines if (line.narration or "").strip()]
    if not emotions:
        return "neutral"
    counts = Counter(emotions)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


_EMOTION_LABELS: dict[str, str] = {
    "sad": "Cinematic cello and felt piano, restrained dynamics, no vocals, loopable underscore",
    "fear": "Eerie low strings and distant pulses, tense cinematic atmosphere, no vocals, loopable",
    "angry": "Driving low percussion and aggressive strings, cinematic action tension, no vocals, loopable",
    "happy": "Warm cinematic plucks and gentle strings, uplifting but subtle, no vocals, loopable",
    "surprised": "Tense rising strings with sharp accents, cinematic suspense, no vocals, loopable",
    "curious": "Light investigative pulses with soft pads, cinematic mystery underscore, no vocals, loopable",
    "confused": "Uncertain ambient textures with subtle dissonance, cinematic unease, no vocals, loopable",
    "determined": "Steady motivational low strings and subtle pulses, forward cinematic drive, no vocals, loopable",
    "hopeful": "Warm rising strings with gentle piano, resilient cinematic optimism, no vocals, loopable",
    "resigned": "Soft low piano and sparse strings, subdued acceptance, no vocals, loopable",
    "pain": "Tight dissonant strings with low pulses, cinematic distress, no vocals, loopable",
    "concerned": "Subtle tense pads and restrained strings, cautious cinematic mood, no vocals, loopable",
    "worried": "Uneasy light pulses with thin strings, anxious cinematic underscore, no vocals, loopable",
    "weak": "Fragile piano motifs with airy pads, faint cinematic tone, no vocals, loopable",
    "urgent": "Driving low pulses and urgent strings, high cinematic tension, no vocals, loopable",
    "nostalgic": "Warm nostalgic piano with soft distant strings, reflective cinematic mood, no vocals, loopable",
    "reassuring": "Gentle uplifting pads with soft piano, calm cinematic comfort, no vocals, loopable",
    "regretful": "Melancholic piano with muted strings, reflective regret, no vocals, loopable",
    "apologetic": "Soft intimate pads with restrained piano, subdued cinematic tone, no vocals, loopable",
    "serious": "Low sustained strings with minimal percussion, grave cinematic tone, no vocals, loopable",
    "desperate": "Frantic strings with pulsing low brass and urgent swells, cinematic desperation, no vocals, loopable",
    "neutral": "Soft neo-classical ambient underscore with airy pads and light strings, no vocals, loopable",
    "frustrated": "Edgy low strings with tight rhythmic pulses, restrained irritation, cinematic tension, no vocals, loopable",
    "teasing": "Playful light pizzicato and soft cheeky plucks, mischievous undertone, no vocals, loopable",
    "defensive": "Guarded low pads with cautious strings, wary protective mood, no vocals, loopable",
}

_MUSIC_TYPE_TO_EMOTION: dict[str, str] = {
    "intense": "angry",
    "tension": "fear",
    "piano": "sad",
    "ambient": "neutral",
    "uplift": "happy",
}


def estimate_script_narration_duration_sec(lines: list[ScriptLine]) -> float:
    total = 0.0
    for line in lines:
        text = (line.narration or "").strip()
        if not text:
            continue
        emo = (line.emotion or "neutral").lower()
        inten = float(line.emotion_intensity if line.emotion_intensity is not None else 0.5)
        pause = pause_seconds(emo, inten)
        total += max(1.2, len(text) * 0.048)
        total += pause
    return max(5.0, total)


def resolve_music_bed(
    lines: list[ScriptLine],
    audio_dir: Path,
    music_type_override: str | None = None,
    scene_id: int | None = None,
) -> tuple[Path | None, str, str]:
    """
    Returns (path_or_none, source, reason).

    Resolution order:
    1) When local library is preferred OR ElevenLabs music is off: materialize from the persisted
       library (``outputs/cache/bgm_library``). Slot choice maps **dominant emotion** to one of 10
       mood families (aligned with library prompts); larger ``BGM_LIBRARY_COUNT`` adds variant
       takes (same mood, ``slot+10``), not random unrelated beds.
    2) When ElevenLabs music is on and library is not preferred: generate per-scene bed (cached).
    3) Fallback: single ``BGM_DEFAULT_PATH`` copy.
    """
    if not settings.audio_bed_in_narration:
        return None, "none", "audio_bed_in_narration_disabled"

    override = (music_type_override or "").strip().lower()
    emotion = _MUSIC_TYPE_TO_EMOTION.get(override) or _dominant_emotion(lines)
    slot = pick_bgm_slot(emotion, scene_id, len(lines))

    use_library_first = bool(settings.bgm_library_prefer_local) or not bool(settings.elevenlabs_music_enabled)

    if use_library_first:
        lib_out = materialize_bed_for_scene(slot, audio_dir)
        if lib_out is not None and lib_out.exists():
            return lib_out, "bgm_library", f"slot_{slot:02d}"

    if settings.elevenlabs_music_enabled:
        duration_ms = int(max(3000, min(600000, estimate_script_narration_duration_sec(lines) * 1000)))
        prompt = music_prompt_for_emotion(emotion)
        out = audio_dir / "music_scene.mp3"
        try:
            generate_scene_music(prompt=prompt, duration_ms=duration_ms, output_path=out)
            return out, "elevenlabs", ""
        except ProviderError:
            lib_out = materialize_bed_for_scene(slot, audio_dir)
            if lib_out is not None and lib_out.exists():
                return lib_out, "bgm_library", "elevenlabs_failed_fallback"
            raise

    # ElevenLabs off and library path failed — try single default file
    default = settings.bgm_default_path
    if default:
        p = Path(str(default)).expanduser()
        if p.is_file():
            out = audio_dir / "music_scene.mp3"
            audio_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            return out, "bgm_default", "library_unavailable_used_default"

    return None, "none", "no_music_source"


def music_prompt_for_emotion(emotion: str) -> str:
    return _EMOTION_LABELS.get((emotion or "neutral").lower(), _EMOTION_LABELS["neutral"])


def _extract_audio_from_multipart(content_type: str, body: bytes) -> bytes:
    """
    Parse multipart/mixed response; return first audio payload part.
    """
    header = f"Content-Type: {content_type}\nMIME-Version: 1.0\n\n".encode("utf-8")
    msg = email.message_from_bytes(header + body)
    if not msg.is_multipart():
        return body
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        if ctype.startswith("audio/") or ctype in {"application/octet-stream", "binary/octet-stream"}:
            payload = part.get_payload(decode=True)
            if payload:
                return payload
    raise ValueError("No audio part found in ElevenLabs music multipart response")


def generate_scene_music(prompt: str, duration_ms: int, output_path: Path) -> None:
    if not settings.elevenlabs_music_enabled:
        raise ProviderError("music_engine", "elevenlabs", "ELEVENLABS_MUSIC_ENABLED is false", "ELEVENLABS_MUSIC_DISABLED")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_ms = int(max(3000, min(600000, duration_ms)))
    cache_key = hash_text(
        f"music|{prompt}|{safe_ms}|{settings.elevenlabs_music_model_id}|{settings.elevenlabs_music_output_format}|"
        f"{settings.elevenlabs_music_force_instrumental}"
    )
    cached = read_cache_bytes("elevenlabs_music", cache_key)
    if cached:
        output_path.write_bytes(cached)
        return

    url = f"{settings.elevenlabs_api_base_url.rstrip('/')}/v1/music/detailed?output_format={settings.elevenlabs_music_output_format}"
    headers = {
        "xi-api-key": str(settings.elevenlabs_api_key),
        "Content-Type": "application/json",
        "Accept": "application/octet-stream",
    }
    payload = {
        "prompt": prompt,
        "music_length_ms": safe_ms,
        "model_id": settings.elevenlabs_music_model_id,
        "force_instrumental": bool(settings.elevenlabs_music_force_instrumental),
    }
    for attempt in range(settings.provider_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=max(settings.provider_timeout_sec, 90))
            if resp.status_code == 429 and attempt < settings.provider_retries:
                time.sleep(1.0 * (2**attempt))
                continue
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            data = _extract_audio_from_multipart(ctype, resp.content)
            output_path.write_bytes(data)
            write_cache_bytes("elevenlabs_music", cache_key, data)
            return
        except Exception as exc:
            if attempt >= settings.provider_retries:
                raise ProviderError(
                    "music_engine",
                    "elevenlabs",
                    f"ElevenLabs music compose failed: {exc}",
                    "ELEVENLABS_MUSIC_FAILED",
                ) from exc
            time.sleep(0.6 * (attempt + 1))
