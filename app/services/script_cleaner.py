from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timezone

from openai import OpenAI

from app.config import settings
from app.models.schemas import OcrResult, ScriptLine
from app.utils.cache_utils import hash_text, read_cache_json, write_cache_json
from app.utils.errors import ProviderError

logger = logging.getLogger(__name__)


def _debug_log_openai_io(stage: str, request_payload: dict, response_text: str | None = None, error: Exception | None = None) -> None:
    if not settings.openai_debug_io:
        return
    logger.info("openai_io stage=%s request=%s", stage, json.dumps(request_payload, ensure_ascii=True))
    if response_text is not None:
        logger.info("openai_io stage=%s response_text=%s", stage, response_text)
    if error is not None:
        logger.info("openai_io stage=%s error=%s", stage, str(error))


def _classify_openai_error(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    normalized = message.lower()
    if "429" in normalized or "rate limit" in normalized or "too many requests" in normalized:
        return ("OPENAI_RATE_LIMITED", f"OpenAI script cleaning rate-limited: {message}")
    if "401" in normalized or "invalid api key" in normalized or "authentication" in normalized:
        return ("OPENAI_AUTH_FAILED", f"OpenAI script cleaning auth failed: {message}")
    if "timeout" in normalized:
        return ("OPENAI_TIMEOUT", f"OpenAI script cleaning timed out: {message}")
    return ("OPENAI_CLEAN_FAILED", f"OpenAI script cleaning failed: {message}")


def _extract_json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "[":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
            if isinstance(parsed, list):
                return parsed
        except Exception:
            continue
    raise ValueError("OpenAI script cleaner JSON array parse failed")


def _parse_retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    value = str(raw).strip()
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds)
    except Exception:
        pass
    try:
        dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


def _retry_sleep_seconds(exc: Exception, attempt: int) -> float:
    retry_after = _parse_retry_after_seconds(exc)
    if retry_after is not None:
        return min(20.0, retry_after + random.uniform(0.05, 0.35))
    base = 1.0 * (2**attempt)
    return min(20.0, base + random.uniform(0.05, 0.35))


def _chunk_ocr(items: list[OcrResult], batch_size: int) -> list[list[OcrResult]]:
    if batch_size <= 0:
        batch_size = 1
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _to_payload(raw_text_list: list[OcrResult]) -> list[dict]:
    return [{"panel_path": item.panel_path, "text": item.text, "low_confidence": item.low_confidence} for item in raw_text_list]


def _normalize_dialogue_text(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    # Suppress repetitive non-semantic sigh/interjection-only outputs.
    filler_patterns = [
        r"^h+u+\.{0,3}$",
        r"^h+a+\.{0,3}$",
        r"^ah+h+\.{0,3}$",
        r"^ha+h+\.{0,3}$",
    ]
    if any(re.match(pat, lowered) for pat in filler_patterns):
        return ""
    # Normalize over-elongated sighs without dropping meaningful words.
    cleaned = re.sub(r"\b(h)(u)\2{2,}\b", r"\1u", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(h)(a)\2{2,}\b", r"\1a", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bha{2,}ppy\b", "happy", cleaned, flags=re.IGNORECASE)
    return cleaned


def _normalize_speaker_and_gender(speaker: str, gender: str) -> tuple[str, str]:
    normalized_speaker = (speaker or "unknown_1").strip().lower()
    allowed_speakers = {"male_1", "male_2", "female_1", "female_2", "narrator", "unknown_1"}
    if normalized_speaker not in allowed_speakers:
        normalized_speaker = "unknown_1"
    normalized_gender = (gender or "unknown").strip().lower()
    if normalized_gender not in {"male", "female", "unknown"}:
        normalized_gender = "unknown"
    # If model identifies a speaker class but misses gender, infer directly.
    if normalized_speaker.startswith("male_"):
        normalized_gender = "male"
    elif normalized_speaker.startswith("female_"):
        normalized_gender = "female"
    elif normalized_speaker == "narrator" and normalized_gender == "unknown":
        normalized_gender = "unknown"
    return normalized_speaker, normalized_gender


def _clean_chunk(client: OpenAI, raw_text_list: list[OcrResult]) -> list[ScriptLine]:
    payload = [{"panel_path": item.panel_path, "text": item.text, "low_confidence": item.low_confidence} for item in raw_text_list]
    non_empty_indices = [
        idx
        for idx, item in enumerate(raw_text_list)
        if (item.text or "").strip()
    ]
    if settings.openai_skip_empty_ocr_for_cleaner and non_empty_indices:
        llm_items = [raw_text_list[idx] for idx in non_empty_indices]
    else:
        llm_items = raw_text_list

    prompt = (
        "You are an expert dialogue analyst for manga and comics.\n"
        "Convert raw OCR lines into structured dialogue JSON.\n"
        "Return ONLY a valid JSON array of objects with keys exactly:\n"
        'text, speaker, gender, emotion\n'
        "speaker should be one of male_1/male_2/female_1/female_2/narrator/unknown_1.\n"
        "gender should be male/female/unknown.\n"
        "emotion should be angry/sad/fear/happy/neutral.\n"
        "Fix OCR errors and punctuation but keep original meaning.\n"
        "Avoid adding filler interjections like 'huuu', 'haa', or repeated sighs unless essential.\n"
        "Keep same speaker ID consistent within the provided sequence.\n"
        "Keep order exactly matching input items. One output object per input item.\n"
        "If text is unreadable or empty, return empty string for text, speaker unknown_1, gender unknown, emotion neutral.\n"
        f"Input OCR items:\n{json.dumps(_to_payload(llm_items), ensure_ascii=True)}"
    )
    request_payload = {
        "model": settings.openai_model,
        "timeout_sec": settings.provider_timeout_sec,
        "items": payload,
    }

    last_error = None
    data = None
    for attempt in range(settings.provider_retries + 1):
        try:
            _debug_log_openai_io("script_cleaner.batch", request_payload)
            response = client.responses.create(
                model=settings.openai_model,
                input=prompt,
                timeout=settings.provider_timeout_sec,
            )
            text = response.output_text.strip()
            _debug_log_openai_io("script_cleaner.batch", request_payload, response_text=text)
            data = _extract_json_array(text)
            last_error = None
            break
        except Exception as exc:
            _debug_log_openai_io("script_cleaner.batch", request_payload, error=exc)
            last_error = exc
            if attempt >= settings.provider_retries:
                break
            delay = _retry_sleep_seconds(exc, attempt)
            logger.warning(
                "script_cleaner retry attempt=%s batch_size=%s delay_sec=%.2f error=%s",
                attempt + 1,
                len(llm_items),
                delay,
                exc,
            )
            time.sleep(delay)
    if last_error is not None:
        error_code, message = _classify_openai_error(last_error)
        raise ProviderError("script_cleaner", "openai", message, error_code) from last_error

    if not isinstance(data, list):
        raise ProviderError("script_cleaner", "openai", "OpenAI returned non-list output", "OPENAI_INVALID_OUTPUT")

    result: list[ScriptLine] = []
    normalized_llm: list[dict] = [item for item in data if isinstance(item, dict)]
    if len(normalized_llm) < len(llm_items):
        normalized_llm.extend([{"text": "", "speaker": "unknown_1", "gender": "unknown", "emotion": "neutral"}] * (len(llm_items) - len(normalized_llm)))
    if len(normalized_llm) > len(llm_items):
        normalized_llm = normalized_llm[: len(llm_items)]
    normalized: list[dict] = [{"text": "", "speaker": "unknown_1", "gender": "unknown", "emotion": "neutral"} for _ in raw_text_list]
    if settings.openai_skip_empty_ocr_for_cleaner and non_empty_indices:
        for i, src_idx in enumerate(non_empty_indices):
            normalized[src_idx] = normalized_llm[i]
    else:
        normalized = normalized_llm

    for idx, item in enumerate(normalized):
        try:
            emotion = str(item.get("emotion", "neutral")).strip().lower()
            if emotion not in {"angry", "sad", "fear", "happy", "neutral"}:
                emotion = "neutral"
            speaker, gender = _normalize_speaker_and_gender(
                speaker=str(item.get("speaker", "unknown_1")),
                gender=str(item.get("gender", "unknown")),
            )
            result.append(
                ScriptLine(
                    panel_path=raw_text_list[idx].panel_path,
                    narration=_normalize_dialogue_text(str(item.get("text", "")).strip()),
                    speaker=speaker,
                    gender=gender,
                    emotion=emotion,
                )
            )
        except Exception as exc:
            raise ProviderError("script_cleaner", "openai", f"OpenAI response schema invalid: {exc}", "OPENAI_SCHEMA_INVALID") from exc
    return result


def clean_script(raw_text_list: list[OcrResult]) -> list[ScriptLine]:
    if not raw_text_list:
        return []

    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    all_lines: list[ScriptLine] = []
    for chunk in _chunk_ocr(raw_text_list, settings.openai_script_batch_size):
        chunk_payload = _to_payload(chunk)
        chunk_key = hash_text(json.dumps(chunk_payload, ensure_ascii=True, sort_keys=True))
        cached = read_cache_json("script_cleaner_chunks", chunk_key)
        if isinstance(cached, list):
            try:
                all_lines.extend([ScriptLine(**item) for item in cached])
                continue
            except Exception:
                pass
        cleaned_chunk = _clean_chunk(client, chunk)
        write_cache_json("script_cleaner_chunks", chunk_key, [line.model_dump() for line in cleaned_chunk])
        all_lines.extend(cleaned_chunk)

    full_cache_key = hash_text(json.dumps(_to_payload(raw_text_list), ensure_ascii=True, sort_keys=True))
    write_cache_json("script_cleaner", full_cache_key, [line.model_dump() for line in all_lines])
    return all_lines
