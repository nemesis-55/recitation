from __future__ import annotations

import json
import logging
import re
import time

from openai import OpenAI

from app.config import settings
from app.models.schemas import SrtTimelineLine
from app.utils.cache_utils import hash_text, read_cache_json, write_cache_json
from app.utils.errors import ProviderError
from app.services.audio.dialogue_analyzer import (
    _is_rate_limited,
    _responses_create_deterministic,
    _retry_sleep_seconds,
)

logger = logging.getLogger(__name__)


def _word_count(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", s or ""))


def _truncate_words(text: str, max_words: int) -> str:
    words = re.findall(r"\S+", text or "")
    if len(words) <= max_words:
        return " ".join(words).strip()
    return " ".join(words[:max_words]).strip().rstrip(",;:") + "..."


def _extract_polished_payload(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        arr = parsed.get("polished")
        if isinstance(arr, list):
            return [x for x in arr if isinstance(x, dict)]
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    raise ValueError("OpenAI narration polish returned invalid JSON shape")


def polish_srt_lines(lines: list[SrtTimelineLine]) -> list[SrtTimelineLine]:
    """
    Rewrite OCR / noisy text into concise spoken narration (batched OpenAI).
    Skips when disabled, no API key, or all lines empty.
    """
    if not lines:
        return lines
    if not settings.openai_narration_polish_enabled:
        return lines
    if settings.use_mock_llm:
        return lines
    if not settings.openai_api_key:
        logger.info("narration_polish skipped (no OPENAI_API_KEY)")
        return lines
    if not any((ln.text or "").strip() for ln in lines):
        return lines

    model = (settings.openai_narration_polish_model or settings.openai_model).strip()
    batch_size = max(1, int(settings.openai_narration_polish_batch_size))
    max_words = max(8, min(48, int(settings.narration_polish_max_words)))
    style = (settings.narration_polish_style or "literary_compact").strip().lower()
    base_interval = max(
        0.0,
        float(settings.openai_dialogue_batch_pace_sec),
        float(settings.openai_dialogue_min_request_interval_sec),
    )
    rate_limit_pressure = 1.0
    last_openai_request_at = 0.0

    cache_key = hash_text(
        json.dumps(
            {
                "narration_polish": "v1",
                "model": model,
                "batch_size": batch_size,
                "max_words": max_words,
                "style": style,
                "lines": [
                    {
                        "index": int(ln.index),
                        "text": str(ln.text or ""),
                    }
                    for ln in lines
                ],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    cached = read_cache_json("narration_polish", cache_key)
    if isinstance(cached, list) and len(cached) == len(lines):
        out_rows = [r for r in cached if isinstance(r, dict)]
        if len(out_rows) == len(lines):
            for i, ln in enumerate(lines):
                t = str(out_rows[i].get("text", "") if i < len(out_rows) else "").strip()
                ln.text = t
            logger.info("narration_polish cache_hit lines=%s", len(lines))
            return lines

    style_hint = (
        "Use vivid, literary but concise phrasing; match horror/mystery tone when the content is dark."
        if "literary" in style
        else "Use clear, neutral spoken English; no flourish."
    )

    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    polished_chunks: list[dict] = []

    for start in range(0, len(lines), batch_size):
        chunk = lines[start : start + batch_size]
        if not any((ln.text or "").strip() for ln in chunk):
            for ln in chunk:
                polished_chunks.append({"index": ln.index, "text": ""})
            continue
        prev_ctx = lines[max(0, start - 2) : start]
        context_block = "\n".join(f"{ln.index}. {ln.text}" for ln in prev_ctx)
        prompt_lines = "\n".join(f"{ln.index}. {ln.text}" for ln in chunk)

        prompt = (
            "You rewrite manga / webtoon OCR into lines meant to be READ ALOUD by a voice actor.\n"
            "Return JSON only. Schema: {\"polished\":[{\"index\":1,\"text\":\"...\"},...]}\n"
            f"Return exactly {len(chunk)} objects, one per target line, in the same order as targets.\n"
            "Rules:\n"
            "- Each `text` must be standalone spoken narration or in-character speech; no stage directions in brackets.\n"
            "- Remove social-media UI: usernames, like counts, 'people like this', comment/share prompts.\n"
            "- Do not read hashtag symbols aloud; fold hashtag meaning into tone in one short phrase if needed, or omit.\n"
            "- Remove redundant words; avoid repeating the same fact as the previous line if context shows duplication.\n"
            f"- HARD CAP: at most {max_words} words per `text`. If OCR is long, summarize the essence.\n"
            f"- Style: {style_hint}\n"
            "- If a line is empty or only noise after rewrite, use empty string \"\".\n"
            "- Preserve story meaning: who speaks, fear, surprise, disgust, etc.\n"
            + (f"Previous lines (context only, do not copy verbatim):\n{context_block}\n\n" if context_block else "")
            + f"Target lines to rewrite:\n{prompt_lines}\n"
        )

        effective_interval = base_interval * rate_limit_pressure
        if last_openai_request_at > 0 and effective_interval > 0:
            elapsed = time.time() - last_openai_request_at
            if elapsed < effective_interval:
                time.sleep(effective_interval - elapsed)

        chunk_rows: list[dict] | None = None
        last_error: Exception | None = None
        for attempt in range(settings.provider_retries + 1):
            try:
                last_openai_request_at = time.time()
                response = _responses_create_deterministic(client, model, prompt)
                chunk_rows = _extract_polished_payload(response.output_text)
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
                        "narration_polish retry attempt=%s batch_size=%s delay_sec=%.2f error=%s",
                        attempt + 1,
                        len(chunk),
                        delay,
                        exc,
                    )
                    time.sleep(delay)

        if chunk_rows is None:
            raise ProviderError(
                "narration_polish",
                "openai",
                f"OpenAI narration polish failed: {last_error}",
                "OPENAI_NARRATION_POLISH_FAILED",
            ) from last_error

        by_index: dict[int, str] = {}
        for row in chunk_rows:
            if not isinstance(row, dict):
                continue
            try:
                ix = int(row.get("index"))
            except Exception:
                continue
            by_index[ix] = str(row.get("text", "") or "").strip()

        for ln in chunk:
            raw_text = by_index.get(ln.index, (ln.text or "").strip())
            if _word_count(raw_text) > max_words:
                raw_text = _truncate_words(raw_text, max_words)
            polished_chunks.append({"index": ln.index, "text": raw_text})
            ln.text = raw_text or ""

        logger.info(
            "narration_polish chunk_done start=%s size=%s",
            start,
            len(chunk),
        )

    write_cache_json("narration_polish", cache_key, polished_chunks)
    return lines
