from __future__ import annotations

import json
from collections import Counter

from openai import OpenAI

from app.config import settings
from app.models.schemas import SrtTimelineLine


def _fallback_scene(lines: list[SrtTimelineLine]) -> dict:
    speakers = [str(ln.speaker or "unknown_1").lower() for ln in lines if (ln.text or "").strip()]
    emotions = [str(ln.emotion or "neutral").lower() for ln in lines if (ln.text or "").strip()]
    if emotions:
        counts = Counter(emotions)
        scene_emotion = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    else:
        scene_emotion = "neutral"
    scene_type = (
        "fight"
        if scene_emotion == "angry"
        else ("emotional" if scene_emotion in {"sad", "fear", "surprised", "confused"} else "neutral")
    )
    uniq = []
    for sp in speakers:
        if sp and sp not in uniq:
            uniq.append(sp)
    characters = []
    for idx, sp in enumerate(uniq, start=1):
        gender = "female" if sp.startswith("female_") else ("male" if sp.startswith("male_") else "unknown")
        characters.append(
            {
                "id": f"char_{idx}",
                "speaker": sp,
                "gender": gender,
                "personality": "neutral",
                "voice_style": "cinematic",
            }
        )
    return {"characters": characters, "scene_type": scene_type, "scene_emotion": scene_emotion}


def analyze_scene(lines: list[SrtTimelineLine]) -> dict:
    if not lines:
        return {"characters": [], "scene_type": "neutral", "scene_emotion": "neutral"}
    if not settings.openai_dialogue_analysis_enabled or not settings.openai_api_key:
        return _fallback_scene(lines)

    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    payload_lines = [f"{ln.index}. {ln.text}" for ln in lines[:80]]
    prompt = (
        "Analyze this subtitle chunk and return ONLY raw JSON object with keys: characters, scene_type, scene_emotion.\n"
        "scene_type must be one of: fight, emotional, neutral.\n"
        "scene_emotion must be one of: angry, fear, sad, neutral, happy, surprised, curious, confused.\n"
        "characters must be array of objects: {id, speaker, gender, personality, voice_style}.\n"
        "No markdown.\n"
        "Lines:\n" + "\n".join(payload_lines)
    )
    try:
        resp = client.responses.create(model=settings.openai_dialogue_analysis_model or settings.openai_model, input=prompt, timeout=settings.provider_timeout_sec, temperature=0)
    except TypeError:
        resp = client.responses.create(model=settings.openai_dialogue_analysis_model or settings.openai_model, input=prompt, timeout=settings.provider_timeout_sec)
    except Exception:
        return _fallback_scene(lines)

    raw = (getattr(resp, "output_text", None) or "").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            scene_type = str(parsed.get("scene_type", "neutral")).strip().lower()
            if scene_type not in {"fight", "emotional", "neutral"}:
                scene_type = "neutral"
            scene_emotion = str(parsed.get("scene_emotion", "neutral")).strip().lower()
            if scene_emotion not in {"angry", "fear", "sad", "neutral", "happy", "surprised", "curious", "confused"}:
                scene_emotion = "neutral"
            chars = parsed.get("characters")
            if not isinstance(chars, list):
                chars = []
            return {"characters": chars, "scene_type": scene_type, "scene_emotion": scene_emotion}
    except Exception:
        pass
    return _fallback_scene(lines)

