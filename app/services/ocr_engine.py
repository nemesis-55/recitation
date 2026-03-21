from __future__ import annotations

import base64
import json
import logging
import random
import re
from pathlib import Path
import time
from datetime import datetime, timezone
from typing import Any, Optional

import cv2
import numpy as np
from openai import OpenAI

from app.config import settings
from app.models.schemas import OcrResult, PanelAsset
from app.utils.cache_utils import hash_bytes, read_cache_json, write_cache_json
from app.utils.errors import ProviderError

logger = logging.getLogger(__name__)


def _debug_log_openai_io(stage: str, request_payload: dict[str, Any], response_text: str | None = None, error: Exception | None = None) -> None:
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
        return ("OPENAI_RATE_LIMITED", f"OpenAI OCR rate-limited: {message}")
    if "401" in normalized or "invalid api key" in normalized or "authentication" in normalized:
        return ("OPENAI_AUTH_FAILED", f"OpenAI OCR authentication failed: {message}")
    if "timeout" in normalized:
        return ("OPENAI_TIMEOUT", f"OpenAI OCR timed out: {message}")
    return ("OPENAI_OCR_FAILED", f"OpenAI OCR failed: {message}")


def _parse_retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw:
            value = str(raw).strip()
            if value:
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
        return min(20.0, retry_after + random.uniform(0.05, 0.35))
    base = 1.0 * (2**attempt)
    return min(20.0, base + random.uniform(0.05, 0.35))


def _read_panel_bytes(panel: PanelAsset) -> bytes:
    path = Path(panel.image_path)
    if not path.exists():
        raise ProviderError(
            "ocr_engine",
            "openai",
            f"Panel image is missing: '{path}'",
            "PANEL_IMAGE_MISSING",
        )
    try:
        return path.read_bytes()
    except Exception as exc:
        raise ProviderError(
            "ocr_engine",
            "openai",
            f"Failed to read panel image: '{path}' ({exc})",
            "PANEL_IMAGE_READ_FAILED",
        ) from exc


def _encode_image_data_url(image_path: str, raw: bytes | None = None) -> str:
    path = Path(image_path)
    raw_bytes = raw if raw is not None else path.read_bytes()
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is not None:
        h, w = image.shape[:2]
        max_dim = max(1, settings.openai_ocr_max_image_dim)
        largest = max(h, w)
        if largest > max_dim:
            scale = max_dim / float(largest)
            resized_w = max(1, int(w * scale))
            resized_h = max(1, int(h * scale))
            image = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
        quality = max(30, min(95, settings.openai_ocr_jpeg_quality))
        ok, encoded_image = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok:
            encoded = base64.b64encode(encoded_image.tobytes()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
    # Fallback to original bytes if decode/encode path fails.
    suffix = path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"

def _extract_output_text(response: Any) -> str:
    text = (getattr(response, "output_text", None) or "").strip()
    return text


def _extract_json_array(raw: str) -> list[Any]:
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
    raise ValueError("OpenAI OCR batch JSON array parse failed")


def _normalize_batch_items(data: list[Any], expected_len: int) -> list[dict[str, Any]]:
    items = [item for item in data if isinstance(item, dict)]
    if len(items) < expected_len:
        items.extend([{"text": "", "confidence": 0.0}] * (expected_len - len(items)))
    elif len(items) > expected_len:
        items = items[:expected_len]
    return items


def _chunk_panels(panels: list[PanelAsset], batch_size: int) -> list[list[PanelAsset]]:
    if batch_size <= 0:
        batch_size = 1
    return [panels[i : i + batch_size] for i in range(0, len(panels), batch_size)]


def extract_text(panel: PanelAsset) -> OcrResult:
    panel_bytes = _read_panel_bytes(panel)
    panel_key = hash_bytes(panel_bytes)
    cached = read_cache_json("ocr_engine", panel_key)
    if isinstance(cached, dict):
        try:
            return OcrResult(**cached)
        except Exception:
            pass

    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    image_data_url = _encode_image_data_url(panel.image_path, raw=panel_bytes)
    prompt = (
        "Extract all readable dialogue/captions from this manga panel. "
        "Return plain text only, no markdown, no explanations. "
        "If there is no readable text, return an empty string."
    )
    request_payload = {
        "model": settings.openai_model,
        "timeout_sec": settings.provider_timeout_sec,
        "panel_path": panel.image_path,
        "prompt": prompt,
    }
    last_error = None
    extracted = ""
    for attempt in range(settings.provider_retries + 1):
        try:
            _debug_log_openai_io("ocr_engine.single", request_payload)
            response = client.responses.create(
                model=settings.openai_model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": image_data_url},
                        ],
                    }
                ],
                timeout=settings.provider_timeout_sec,
            )
            extracted = _extract_output_text(response)
            _debug_log_openai_io("ocr_engine.single", request_payload, response_text=extracted)
            last_error = None
            break
        except Exception as exc:
            _debug_log_openai_io("ocr_engine.single", request_payload, error=exc)
            last_error = exc
            if attempt < settings.provider_retries:
                delay = _retry_sleep_seconds(exc, attempt)
                logger.warning(
                    "ocr_engine panel retry attempt=%s delay_sec=%.2f error=%s",
                    attempt + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
    if last_error is not None:
        error_code, message = _classify_openai_error(last_error)
        raise ProviderError("ocr_engine", "openai", message, error_code) from last_error

    confidence = 0.9 if extracted else 0.0
    result = OcrResult(
        panel_path=str(Path(panel.image_path)),
        text=extracted,
        confidence=confidence,
        low_confidence=not bool(extracted.strip()),
    )
    write_cache_json("ocr_engine", panel_key, result.model_dump())
    return result


def _extract_text_batch_once(client: OpenAI, panels: list[dict[str, Any]]) -> list[OcrResult]:
    prompt = (
        "You will receive multiple manga panel images.\n"
        "For each image, extract readable dialogue/captions only.\n"
        "Return strict JSON array in the same order as images, with objects:\n"
        '{"text":"...","confidence":0.0}\n'
        "Confidence must be 0.0 to 1.0. If no text, use empty text and confidence 0.0."
    )
    content = [{"type": "input_text", "text": prompt}]
    panel_paths: list[str] = []
    for item in panels:
        panel = item["panel"]
        panel_paths.append(panel.image_path)
        content.append({"type": "input_image", "image_url": _encode_image_data_url(panel.image_path, raw=item["bytes"])})
    request_payload = {
        "model": settings.openai_model,
        "timeout_sec": settings.provider_timeout_sec,
        "panel_count": len(panels),
        "panel_paths": panel_paths,
        "prompt": prompt,
    }

    _debug_log_openai_io("ocr_engine.batch", request_payload)
    response = client.responses.create(
        model=settings.openai_model,
        input=[{"role": "user", "content": content}],
        timeout=settings.provider_timeout_sec,
    )
    raw = _extract_output_text(response)
    _debug_log_openai_io("ocr_engine.batch", request_payload, response_text=raw)
    data = _normalize_batch_items(_extract_json_array(raw), len(panels))

    results: list[OcrResult] = []
    for panel_info, item in zip(panels, data):
        panel = panel_info["panel"]
        text = str(item.get("text", "")).strip()
        conf = float(item.get("confidence", 0.0))
        conf = max(0.0, min(1.0, conf))
        result = OcrResult(
            panel_path=str(Path(panel.image_path)),
            text=text,
            confidence=conf,
            low_confidence=conf < 0.45 or not bool(text),
        )
        write_cache_json("ocr_engine", panel_info["panel_key"], result.model_dump())
        results.append(result)
    return results


def extract_text_batch(panels: list[PanelAsset]) -> list[OcrResult]:
    if not panels:
        return []
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    configured_batch_size = settings.openai_ocr_batch_size
    min_batch_size = 1
    final_results: list[OcrResult] = []
    idx = 0
    current_batch_size = max(min_batch_size, configured_batch_size)
    recovery_cooldown = 0
    success_streak = 0
    logger.info(
        "ocr_engine progress total_panels=%s initial_batch_size=%s",
        len(panels),
        current_batch_size,
    )
    while idx < len(panels):
        panel_group = panels[idx : idx + current_batch_size]
        logger.info(
            "ocr_engine progress preparing_batch start_index=%s batch_size=%s",
            idx,
            len(panel_group),
        )
        uncached: list[dict[str, Any]] = []
        for panel in panel_group:
            panel_bytes = _read_panel_bytes(panel)
            panel_key = hash_bytes(panel_bytes)
            cached = read_cache_json("ocr_engine", panel_key)
            if isinstance(cached, dict):
                try:
                    final_results.append(OcrResult(**cached))
                    continue
                except Exception:
                    pass
            uncached.append({"panel": panel, "bytes": panel_bytes, "panel_key": panel_key})
        if not uncached:
            logger.info(
                "ocr_engine progress batch_cached start_index=%s batch_size=%s",
                idx,
                len(panel_group),
            )
            idx += len(panel_group)
            continue
        last_error = None
        group_results: Optional[list[OcrResult]] = None
        for attempt in range(settings.provider_retries + 1):
            try:
                group_results = _extract_text_batch_once(client, uncached)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < settings.provider_retries:
                    delay = _retry_sleep_seconds(exc, attempt)
                    logger.warning(
                        "ocr_engine batch retry attempt=%s batch_size=%s delay_sec=%.2f error=%s",
                        attempt + 1,
                        len(uncached),
                        delay,
                        exc,
                    )
                    time.sleep(delay)
        if group_results is not None:
            final_results.extend(group_results)
            idx += len(panel_group)
            success_streak += 1
            if recovery_cooldown > 0:
                recovery_cooldown -= 1
            logger.info(
                "ocr_engine progress batch_done completed=%s/%s current_batch_size=%s",
                idx,
                len(panels),
                current_batch_size,
            )
            if (
                current_batch_size < configured_batch_size
                and recovery_cooldown == 0
                and success_streak >= settings.openai_ocr_recovery_batches
            ):
                current_batch_size = min(configured_batch_size, current_batch_size + 1)
                success_streak = 0
        else:
            error_code, message = _classify_openai_error(last_error or RuntimeError("Unknown OpenAI OCR batch failure"))
            if error_code == "OPENAI_RATE_LIMITED" and current_batch_size > min_batch_size:
                # Downshift batch size under pressure, then retry same index.
                current_batch_size = max(min_batch_size, current_batch_size // 2)
                success_streak = 0
                recovery_cooldown = max(recovery_cooldown, settings.openai_ocr_recovery_batches)
                delay = _retry_sleep_seconds(last_error or RuntimeError("rate limited"), settings.provider_retries)
                logger.warning(
                    "ocr_engine downshift batch_size=%s next_delay_sec=%.2f",
                    current_batch_size,
                    delay,
                )
                time.sleep(delay)
                continue
            error_code, message = _classify_openai_error(last_error or RuntimeError("Unknown OpenAI OCR batch failure"))
            raise ProviderError("ocr_engine", "openai", f"OpenAI OCR batch failed: {message}", error_code) from last_error
    return final_results
