from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from openai import OpenAI

from app.config import settings
from app.models.schemas import SrtTimelineLine
from app.models.schemas import ScriptLine
from app.utils.cache_utils import hash_text, read_cache_json, write_cache_json
from app.utils.errors import ProviderError
from app.services.audio.emotion_constants import ALLOWED_EMOTIONS, emotion_prompt_list

logger = logging.getLogger(__name__)
_VALID_SPEAKERS = {
    "male_1",
    "male_2",
    "male_3",
    "male_4",
    "male_5",
    "male_6",
    "male_7",
    "female_1",
    "female_2",
    "female_3",
    "narrator",
    "unknown_1",
}
_VALID_EMOTIONS = ALLOWED_EMOTIONS


def estimate_emotion_intensity(text: str, emotion: str) -> float:
    base = {
        "angry": 0.8,
        "sad": 0.6,
        "fear": 0.76,
        "happy": 0.7,
        "neutral": 0.38,
        "surprised": 0.78,
        "curious": 0.56,
        "confused": 0.62,
        "determined": 0.72,
        "hopeful": 0.66,
        "resigned": 0.48,
        "pain": 0.78,
        "concerned": 0.6,
        "worried": 0.66,
        "weak": 0.4,
        "urgent": 0.82,
        "nostalgic": 0.52,
        "reassuring": 0.56,
        "regretful": 0.54,
        "apologetic": 0.5,
        "serious": 0.64,
        "desperate": 0.8,
        "frustrated": 0.74,
        "teasing": 0.58,
        "defensive": 0.62,
    }.get(emotion, 0.52)
    bonus = 0.0
    if "!" in text:
        bonus += 0.1
    if "..." in text:
        bonus += 0.07
    if text.isupper() and len(text) >= 6:
        bonus += 0.09
    return max(0.0, min(1.0, base + bonus))


def analyze_dialogue(script: list[ScriptLine]) -> list[ScriptLine]:
    for line in script:
        if line.emotion_intensity is None:
            line.emotion_intensity = estimate_emotion_intensity(line.narration or "", line.emotion or "neutral")
    return script


def _extract_json(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        arr = parsed.get("analysis")
        if isinstance(arr, list):
            return [x for x in arr if isinstance(x, dict)]
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    raise ValueError("OpenAI dialogue analyzer returned invalid JSON shape")


def _normalize_chunk_rows(rows: list[dict], expected_len: int) -> list[dict]:
    items = [r for r in rows if isinstance(r, dict)]
    if len(items) == expected_len:
        return items
    if len(items) > expected_len:
        logger.warning(
            "dialogue_analyzer normalize oversized_response got=%s expected=%s truncating=true",
            len(items),
            expected_len,
        )
        return items[:expected_len]
    logger.warning(
        "dialogue_analyzer normalize undersized_response got=%s expected=%s padding=true",
        len(items),
        expected_len,
    )
    items.extend([{} for _ in range(expected_len - len(items))])
    return items


def _parse_retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw:
            value = str(raw).strip()
            if value:
                try:
                    return max(0.0, float(value))
                except Exception:
                    pass
                try:
                    dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
                    delta = (dt - datetime.now(timezone.utc)).total_seconds()
                    return max(0.0, delta)
                except Exception:
                    pass
    message = str(exc)
    ms_match = re.search(r"try again in\s*([0-9]+(?:\.[0-9]+)?)\s*ms", message, flags=re.IGNORECASE)
    if ms_match:
        return max(0.0, float(ms_match.group(1)) / 1000.0)
    sec_match = re.search(r"try again in\s*([0-9]+(?:\.[0-9]+)?)\s*s", message, flags=re.IGNORECASE)
    if sec_match:
        return max(0.0, float(sec_match.group(1)))
    return None


def _retry_sleep_seconds(exc: Exception, attempt: int) -> float:
    retry_after = _parse_retry_after_seconds(exc)
    if retry_after is not None:
        return min(20.0, retry_after + (0.1 * max(0, attempt)))
    base = 1.0 * (2**attempt)
    return min(20.0, base + (0.1 * max(0, attempt)))


def _is_rate_limited(exc: Exception) -> bool:
    normalized = str(exc).lower()
    return "429" in normalized or "rate limit" in normalized or "too many requests" in normalized


def _responses_create_deterministic(client: OpenAI, model: str, prompt: str):
    base_kwargs = {
        "model": model,
        "input": prompt,
        "timeout": settings.provider_timeout_sec,
    }
    try:
        return client.responses.create(temperature=0, **base_kwargs)
    except TypeError:
        return client.responses.create(**base_kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        if "temperature" in msg and ("unsupported" in msg or "unknown" in msg or "invalid" in msg):
            return client.responses.create(**base_kwargs)
        raise


def _gender_from_speaker(speaker: str) -> str:
    sp = (speaker or "").strip().lower()
    if sp.startswith("male_"):
        return "male"
    if sp.startswith("female_"):
        return "female"
    return "other"


def _has_turn_marker(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return t.startswith(("-", "—", "\"", "'"))


def _flip_same_gender_slot(speaker: str) -> str:
    if speaker == "male_1":
        return "male_2"
    if speaker == "male_2":
        return "male_1"
    if speaker == "male_3":
        return "male_1"
    if speaker == "male_4":
        return "male_2"
    if speaker == "male_5":
        return "male_1"
    if speaker == "male_6":
        return "male_2"
    if speaker == "male_7":
        return "male_1"
    if speaker == "female_1":
        return "female_2"
    if speaker == "female_2":
        return "female_1"
    if speaker == "female_3":
        return "female_1"
    return speaker


def _enforce_speaker_consistency(rows: list[dict], lines: list[SrtTimelineLine]) -> list[dict]:
    fixed: list[dict] = []
    prev_speaker = ""
    prev_text = ""
    run_len = 0
    for idx, row in enumerate(rows):
        item = dict(row)
        speaker = str(item.get("speaker", "unknown_1")).strip().lower()
        text = lines[idx].text if idx < len(lines) else ""
        gender = _gender_from_speaker(speaker)
        if speaker == prev_speaker:
            run_len += 1
        else:
            run_len = 1
        # Conservative disambiguation only when a turn marker strongly suggests a new speaker.
        if (
            run_len >= 2
            and gender in {"male", "female"}
            and speaker in _VALID_SPEAKERS
            and speaker not in {"narrator", "unknown_1"}
            and _has_turn_marker(prev_text)
            and _has_turn_marker(text)
        ):
            speaker = _flip_same_gender_slot(speaker)
            item["speaker"] = speaker
            run_len = 1
        fixed.append(item)
        prev_speaker = speaker
        prev_text = text
    return fixed


def analyze_srt_timeline(lines: list[SrtTimelineLine]) -> list[SrtTimelineLine]:
    if not lines:
        return lines
    if not settings.openai_dialogue_analysis_enabled:
        for ln in lines:
            ln.speaker = "unknown_1"
            ln.emotion = "neutral"
            ln.intensity = estimate_emotion_intensity(ln.text, "neutral")
        return lines

    model = (settings.openai_dialogue_analysis_model or settings.openai_model).strip()
    batch_size = max(1, int(settings.openai_dialogue_batch_size))
    base_interval = max(
        0.0,
        float(settings.openai_dialogue_batch_pace_sec),
        float(settings.openai_dialogue_min_request_interval_sec),
    )
    rate_limit_pressure = 1.0
    last_openai_request_at = 0.0
    rows: list[dict] = []
    cache_key = hash_text(
        json.dumps(
            {
                "emotion_schema": "v5",
                "model": model,
                "batch_size": batch_size,
                "lines": [
                    {
                        "index": int(ln.index),
                        "start_sec": round(float(ln.start_sec), 3),
                        "end_sec": round(float(ln.end_sec), 3),
                        "text": str(ln.text or ""),
                    }
                    for ln in lines
                ],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    cached_rows = read_cache_json("dialogue_analyzer", cache_key)
    if isinstance(cached_rows, list) and len(cached_rows) == len(lines):
        rows = [r for r in cached_rows if isinstance(r, dict)]
        if len(rows) == len(lines):
            for i, row in enumerate(rows):
                sp = str(row.get("speaker", "unknown_1")).strip().lower()
                if sp not in _VALID_SPEAKERS:
                    sp = "unknown_1"
                emo = str(row.get("emotion", "neutral")).strip().lower()
                if emo not in _VALID_EMOTIONS:
                    emo = "neutral"
                try:
                    inten = float(row.get("intensity", estimate_emotion_intensity(lines[i].text, emo)))
                except Exception:
                    inten = estimate_emotion_intensity(lines[i].text, emo)
                inten = max(0.0, min(1.0, inten))
                lines[i].speaker = sp
                lines[i].emotion = emo
                lines[i].intensity = inten
            logger.info("dialogue_analyzer cache_hit lines=%s", len(lines))
            return lines
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    logger.info(
        "dialogue_analyzer start total_lines=%s batch_size=%s base_interval_sec=%.2f",
        len(lines),
        batch_size,
        base_interval,
    )
    for start in range(0, len(lines), batch_size):
        chunk = lines[start : start + batch_size]
        context = lines[max(0, start - 2) : start]
        context_lines = [f"{ln.index}. {ln.text}" for ln in context]
        prompt_lines = [f"{ln.index}. {ln.text}" for ln in chunk]
        prompt = (
            "You are an advanced cinematic manga narrator and dialogue director.\n"
            "Analyze subtitle lines for voice direction and return JSON only.\n"
            "Lines may include OCR from social-media framed panels (usernames, UI, hashtags); "
            "infer speaker and emotion from in-story speech and caption intent, not platform chrome.\n"
            "Schema: {\"analysis\":[{\"speaker\":\"...\",\"emotion\":\"...\",\"intensity\":0.0}]}\n"
            f"Return exactly {len(chunk)} analysis rows in input order.\n"
            "speaker: male_1..male_7, female_1..female_3, narrator, unknown_1.\n"
            f"emotion: {emotion_prompt_list()}.\n"
            "intensity: float in [0,1] — use the full range; avoid clustering near 0.45–0.55 unless the line is truly flat.\n"
            "Push intensity up for clear affect (fear, anger, joy, shock); theatrical, readable delivery.\n"
            "Do not rewrite, merge, or skip any target line; classify each one exactly once.\n"
            "Use gendered speaker IDs when possible; narrator only for non-dialogue narration.\n"
            "{\"analysis\":[{\"speaker\":\"male_1\",\"emotion\":\"neutral\",\"intensity\":0.42}]}\n"
            + ("Previous lines (context only):\n" + "\n".join(context_lines) + "\n" if context_lines else "")
            + "Target lines:\n"
            + "\n".join(prompt_lines)
        )
        effective_interval = base_interval * rate_limit_pressure
        if last_openai_request_at > 0 and effective_interval > 0:
            elapsed = time.time() - last_openai_request_at
            if elapsed < effective_interval:
                time.sleep(effective_interval - elapsed)
        last_error: Exception | None = None
        chunk_rows: list[dict] | None = None
        for attempt in range(settings.provider_retries + 1):
            try:
                last_openai_request_at = time.time()
                response = _responses_create_deterministic(client, model, prompt)
                chunk_rows = _extract_json(response.output_text)
                rate_limit_pressure = max(1.0, rate_limit_pressure * 0.9)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                last_openai_request_at = time.time()
                if _is_rate_limited(exc):
                    rate_limit_pressure = min(4.0, rate_limit_pressure * 1.35)
                if attempt < settings.provider_retries:
                    delay = _retry_sleep_seconds(exc, attempt)
                    if _is_rate_limited(exc):
                        delay = max(
                            delay,
                            float(settings.openai_dialogue_rate_limit_cooldown_sec) * rate_limit_pressure,
                        )
                    logger.warning(
                        "dialogue_analyzer retry attempt=%s batch_size=%s delay_sec=%.2f error=%s",
                        attempt + 1,
                        len(chunk),
                        delay,
                        exc,
                    )
                    time.sleep(delay)
        if chunk_rows is None:
            raise ProviderError(
                "dialogue_analyzer",
                "openai",
                f"OpenAI dialogue analysis failed: {last_error}",
                "OPENAI_DIALOGUE_ANALYSIS_FAILED",
            ) from last_error
        chunk_rows = _normalize_chunk_rows(chunk_rows, len(chunk))
        chunk_rows = _enforce_speaker_consistency(chunk_rows, chunk)
        rows.extend(chunk_rows)
        logger.info(
            "dialogue_analyzer chunk_done start=%s size=%s processed=%s/%s",
            start,
            len(chunk),
            min(len(lines), start + len(chunk)),
            len(lines),
        )

    write_cache_json("dialogue_analyzer", cache_key, rows)

    for i, row in enumerate(rows):
        sp = str(row.get("speaker", "unknown_1")).strip().lower()
        if sp not in _VALID_SPEAKERS:
            logger.info("dialogue_analyzer normalize invalid_speaker index=%s raw=%s", i, sp)
            sp = "unknown_1"
        emo = str(row.get("emotion", "neutral")).strip().lower()
        if emo not in _VALID_EMOTIONS:
            logger.info("dialogue_analyzer normalize invalid_emotion index=%s raw=%s", i, emo)
            emo = "neutral"
        try:
            inten = float(row.get("intensity", estimate_emotion_intensity(lines[i].text, emo)))
        except Exception:
            inten = estimate_emotion_intensity(lines[i].text, emo)
        inten = max(0.0, min(1.0, inten))
        lines[i].speaker = sp
        lines[i].emotion = emo
        lines[i].intensity = inten
    return lines
