"""
OCR → structured script lines (OpenAI). One JSON object per panel, same order as input.

OCR text is never dropped: if the model shortens a line, we keep the full OCR string; if the
model omits tokens, we append missing OCR tokens; unspaced OCR blocks (e.g. CJK) are appended
when absent. LLM output is still used when it is a strict superset of OCR (typo fixes / additions).
"""
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

_ALLOWED_SPEAKERS = frozenset({"male_1", "male_2", "female_1", "female_2", "narrator", "unknown_1"})
_ALLOWED_EMOTIONS = frozenset({"angry", "sad", "fear", "happy", "neutral"})
_DEFAULT_ROW = {"text": "", "speaker": "unknown_1", "gender": "unknown", "emotion": "neutral"}


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
    if "429" in normalized or "rate limit" in normalized:
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
    try:
        return max(0.0, float(value))
    except Exception:
        pass
    try:
        dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def _retry_sleep_seconds(exc: Exception, attempt: int) -> float:
    retry_after = _parse_retry_after_seconds(exc)
    if retry_after is not None:
        return min(20.0, retry_after + random.uniform(0.05, 0.35))
    return min(20.0, 1.0 * (2**attempt) + random.uniform(0.05, 0.35))


def _chunk_ocr(items: list[OcrResult], batch_size: int) -> list[list[OcrResult]]:
    if batch_size <= 0:
        batch_size = 1
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _to_payload(items: list[OcrResult]) -> list[dict]:
    return [{"panel_path": o.panel_path, "text": o.text, "low_confidence": o.low_confidence} for o in items]


def _normalize_dialogue_text(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    # Collapse stretched gasps to a short token (keep TTS-friendly vocals).
    cleaned = re.sub(r"\b(h)u{3,}\b", r"\1uu", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(h)a{3,}\b", r"\1aa", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bha{2,}ppy\b", "happy", cleaned, flags=re.IGNORECASE)
    return cleaned


def _append_missing_ocr_tokens(ocr_normalized: str, candidate: str) -> str:
    """Append whitespace-separated OCR tokens missing from candidate (case-insensitive)."""
    cand_cf = candidate.casefold()
    tokens = re.findall(r"\S+", ocr_normalized)
    missing = [t for t in tokens if t.casefold() not in cand_cf]
    if not missing:
        return candidate
    return _normalize_dialogue_text(f"{candidate} {' '.join(missing)}".strip())


def _merge_llm_and_ocr(llm_text: str, ocr_text: str) -> str:
    """
    Build narration that never drops OCR content: if the model shortens or paraphrases,
    we keep OCR words (full OCR when the model is only a substring of OCR).
    """
    llm = (llm_text or "").strip()
    ocr = (ocr_text or "").strip()
    if not ocr:
        return _normalize_dialogue_text(llm)
    if not llm:
        return _normalize_dialogue_text(ocr)

    ocr_n = _normalize_dialogue_text(ocr)
    llm_n = _normalize_dialogue_text(llm)

    # Model output is a substring of OCR (or equal) — always keep full OCR text.
    if llm_n.casefold() in ocr_n.casefold():
        return ocr_n

    # OCR fully contained in model output — safe to use expanded/cleaned LLM text.
    if ocr_n.casefold() in llm_n.casefold():
        return llm_n

    # Overlap / reordering: tack on any OCR tokens absent from the LLM line.
    return _append_missing_ocr_tokens(ocr_n, llm_n)


def _final_ocr_safety_net(ocr_raw: str, narration: str) -> str:
    """
    Ensure no OCR token (and unspaced OCR lines) are lost. If the full OCR string is already
    contained in narration, keep narration so LLM additions (e.g. extra words) stay.
    """
    ocr_n = _normalize_dialogue_text(ocr_raw).strip()
    if not ocr_n:
        return _normalize_dialogue_text(narration)
    nar_n = _normalize_dialogue_text(narration).strip()
    if ocr_n.casefold() in nar_n.casefold():
        return nar_n
    supplemented = _append_missing_ocr_tokens(ocr_n, nar_n)
    if supplemented.casefold() != nar_n.casefold():
        return supplemented
    # Unspaced OCR (e.g. one CJK line): if the whole block is missing, append it.
    if not re.search(r"\s", ocr_n) and ocr_n.casefold() not in nar_n.casefold():
        return _normalize_dialogue_text(f"{nar_n} {ocr_n}".strip()) if nar_n else ocr_n
    return nar_n


def _normalize_speaker_and_gender(speaker: str, gender: str) -> tuple[str, str]:
    sp = (speaker or "unknown_1").strip().lower()
    if sp not in _ALLOWED_SPEAKERS:
        sp = "unknown_1"
    gd = (gender or "unknown").strip().lower()
    if gd not in {"male", "female", "unknown"}:
        gd = "unknown"
    if sp.startswith("male_"):
        gd = "male"
    elif sp.startswith("female_"):
        gd = "female"
    return sp, gd


def _build_prompt(ocr_json: str) -> str:
    return (
        "You turn manga/comic OCR lines into dialogue for text-to-speech.\n"
        "Return ONLY a JSON array. One object per input row, same order.\n"
        "Each object keys: text, speaker, gender, emotion\n"
        "- text: cleaned line for TTS. You MUST include every word/token from the OCR line; fix typos only, do not omit. "
        "- speaker: male_1 | male_2 | female_1 | female_2 | narrator | unknown_1\n"
        "- gender: male | female | unknown\n"
        "- emotion: angry | sad | fear | happy | neutral\n"
        "If OCR text is empty/unreadable: text=\"\", speaker unknown_1, gender unknown, emotion neutral.\n"
        f"OCR items:\n{ocr_json}"
    )


def _clean_chunk(client: OpenAI, raw_text_list: list[OcrResult]) -> list[ScriptLine]:
    non_empty_idx = [i for i, o in enumerate(raw_text_list) if (o.text or "").strip()]
    if settings.openai_skip_empty_ocr_for_cleaner and non_empty_idx:
        llm_rows = [raw_text_list[i] for i in non_empty_idx]
    else:
        llm_rows = raw_text_list

    prompt = _build_prompt(json.dumps(_to_payload(llm_rows), ensure_ascii=True))
    request_payload = {"model": settings.openai_model, "batch_size": len(llm_rows)}

    last_error = None
    data: list | None = None
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
            time.sleep(_retry_sleep_seconds(exc, attempt))

    if last_error is not None:
        code, msg = _classify_openai_error(last_error)
        raise ProviderError("script_cleaner", "openai", msg, code) from last_error
    if not isinstance(data, list):
        raise ProviderError("script_cleaner", "openai", "OpenAI returned non-list output", "OPENAI_INVALID_OUTPUT")

    rows = [x for x in data if isinstance(x, dict)]
    while len(rows) < len(llm_rows):
        rows.append(dict(_DEFAULT_ROW))
    rows = rows[: len(llm_rows)]

    normalized: list[dict] = [dict(_DEFAULT_ROW) for _ in raw_text_list]
    if settings.openai_skip_empty_ocr_for_cleaner and non_empty_idx:
        for j, src_i in enumerate(non_empty_idx):
            normalized[src_i] = rows[j]
    else:
        normalized = rows

    result: list[ScriptLine] = []
    for idx, item in enumerate(normalized):
        try:
            emo = str(item.get("emotion", "neutral")).strip().lower()
            if emo not in _ALLOWED_EMOTIONS:
                emo = "neutral"
            sp, gd = _normalize_speaker_and_gender(str(item.get("speaker", "")), str(item.get("gender", "")))
            llm_t = str(item.get("text", "")).strip()
            ocr_t = (raw_text_list[idx].text or "").strip()
            narration = _merge_llm_and_ocr(llm_t, ocr_t)
            narration = _final_ocr_safety_net(ocr_t, narration)
            if not narration and ocr_t:
                narration = _normalize_dialogue_text(ocr_t)
            result.append(
                ScriptLine(panel_path=raw_text_list[idx].panel_path, narration=narration, speaker=sp, gender=gd, emotion=emo)
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
        key = hash_text(json.dumps(_to_payload(chunk), ensure_ascii=True, sort_keys=True))
        cached = read_cache_json("script_cleaner_chunks", key)
        if isinstance(cached, list):
            try:
                all_lines.extend([ScriptLine(**item) for item in cached])
                continue
            except Exception:
                pass
        cleaned = _clean_chunk(client, chunk)
        write_cache_json("script_cleaner_chunks", key, [line.model_dump() for line in cleaned])
        all_lines.extend(cleaned)

    full_key = hash_text(json.dumps(_to_payload(raw_text_list), ensure_ascii=True, sort_keys=True))
    write_cache_json("script_cleaner", full_key, [line.model_dump() for line in all_lines])
    return all_lines
