from __future__ import annotations

import json

from openai import OpenAI

from app.config import settings
from app.utils.cache_utils import hash_text, read_cache_json, write_cache_json
from app.services.audio.emotion_constants import ALLOWED_EMOTIONS, emotion_prompt_list


def analyze_emotion(text: str, scene_emotion: str, default_emotion: str, default_intensity: float) -> tuple[str, float]:
    base_emotion = (default_emotion or "neutral").lower()
    base_intensity = max(0.0, min(1.0, float(default_intensity)))
    if not text.strip():
        return base_emotion, base_intensity
    if not settings.openai_dialogue_analysis_enabled or not settings.openai_api_key:
        return base_emotion, base_intensity

    cache_key = hash_text(
        json.dumps(
            {
                "emotion_schema": "v4",
                "text": text,
                "scene_emotion": scene_emotion,
                "default_emotion": base_emotion,
                "default_intensity": round(base_intensity, 3),
                "model": settings.openai_dialogue_analysis_model or settings.openai_model,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    cached = read_cache_json("emotion_engine", cache_key)
    if isinstance(cached, dict):
        try:
            emo = str(cached.get("emotion", base_emotion)).strip().lower()
            if emo not in ALLOWED_EMOTIONS:
                emo = base_emotion
            inten = float(cached.get("intensity", base_intensity))
            inten = max(0.0, min(1.0, inten))
            return emo, inten
        except Exception:
            pass

    prompt = (
        "You are an advanced cinematic manga narrator focused on faithful delivery.\n"
        "Classify the line emotion for performance.\n"
        "Return ONLY raw JSON with keys emotion and intensity.\n"
        f"emotion must be one of: {emotion_prompt_list()}.\n"
        "intensity must be float 0..1.\n"
        "Do not rewrite the line and do not invent details.\n"
        f"scene_emotion: {scene_emotion}\n"
        f"line: {text}"
    )
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    try:
        try:
            resp = client.responses.create(model=settings.openai_dialogue_analysis_model or settings.openai_model, input=prompt, timeout=settings.provider_timeout_sec, temperature=0)
        except TypeError:
            resp = client.responses.create(model=settings.openai_dialogue_analysis_model or settings.openai_model, input=prompt, timeout=settings.provider_timeout_sec)
    except Exception:
        return base_emotion, base_intensity
    raw = (getattr(resp, "output_text", None) or "").strip()
    try:
        parsed = json.loads(raw)
        emo = str(parsed.get("emotion", base_emotion)).strip().lower()
        if emo not in ALLOWED_EMOTIONS:
            emo = base_emotion
        inten = float(parsed.get("intensity", base_intensity))
        inten = max(0.0, min(1.0, inten))
        write_cache_json("emotion_engine", cache_key, {"emotion": emo, "intensity": inten})
        return emo, inten
    except Exception:
        return base_emotion, base_intensity

