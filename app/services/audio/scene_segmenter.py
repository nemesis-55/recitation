from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import settings
from app.models.schemas import SrtTimelineLine


def _fallback_segment(lines: list[SrtTimelineLine]) -> list[dict[str, Any]]:
    if not lines:
        return []
    scenes: list[dict[str, Any]] = []
    start = 0
    scene_id = 1
    for idx in range(1, len(lines)):
        prev = lines[idx - 1]
        cur = lines[idx]
        gap = max(0.0, float(cur.start_sec) - float(prev.end_sec))
        emotion_shift = (prev.emotion or "neutral") != (cur.emotion or "neutral")
        speaker_shift = (prev.speaker or "unknown_1") != (cur.speaker or "unknown_1")
        if gap > float(settings.scene_segment_fallback_gap_sec) or (emotion_shift and speaker_shift):
            scenes.append(
                {
                    "scene_id": scene_id,
                    "panel_range": [start + 1, idx],
                    "description": f"scene_{scene_id}",
                }
            )
            scene_id += 1
            start = idx
    scenes.append(
        {
            "scene_id": scene_id,
            "panel_range": [start + 1, len(lines)],
            "description": f"scene_{scene_id}",
        }
    )
    return scenes


def _segment_chunk(chunk: list[SrtTimelineLine], chunk_start: int, expected_total: int) -> list[dict[str, Any]]:
    prompt_lines = [f"{ln.index}. [{ln.speaker}|{ln.emotion}] {ln.text}" for ln in chunk]
    prompt = (
        "Segment this episode into coherent scenes based on location, continuous dialogue and character continuity.\n"
        "Return ONLY raw JSON array. Each item keys: scene_id, panel_range [start,end], description.\n"
        "panel_range is 1-indexed and inclusive.\n"
        "No markdown.\n"
        "Lines:\n" + "\n".join(prompt_lines)
    )
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    try:
        try:
            resp = client.responses.create(
                model=settings.openai_dialogue_analysis_model or settings.openai_model,
                input=prompt,
                timeout=settings.provider_timeout_sec,
                temperature=0,
            )
        except TypeError:
            resp = client.responses.create(
                model=settings.openai_dialogue_analysis_model or settings.openai_model,
                input=prompt,
                timeout=settings.provider_timeout_sec,
            )
    except Exception:
        return _fallback_segment(chunk)
    raw = (getattr(resp, "output_text", None) or "").strip()
    chunk_lo = int(chunk_start) + 1
    chunk_hi = int(chunk_start) + len(chunk)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            out: list[dict[str, Any]] = []
            for i, item in enumerate(parsed, start=1):
                if not isinstance(item, dict):
                    continue
                pr = item.get("panel_range")
                if not isinstance(pr, list) or len(pr) != 2:
                    continue
                try:
                    lo = int(pr[0])
                    hi = int(pr[1])
                except Exception:
                    continue
                # LLM returns chunk-local ranges; convert to global indices.
                lo = max(1, lo)
                hi = max(lo, hi)
                g_lo = chunk_start + lo
                g_hi = chunk_start + hi
                g_lo = max(chunk_lo, min(chunk_hi, g_lo))
                g_hi = max(g_lo, min(chunk_hi, g_hi))
                g_lo = max(1, min(expected_total, g_lo))
                g_hi = max(g_lo, min(expected_total, g_hi))
                out.append(
                    {
                        "scene_id": int(item.get("scene_id") or i),
                        "panel_range": [g_lo, g_hi],
                        "description": str(item.get("description") or f"scene_{i}"),
                    }
                )
            if out:
                return out
    except Exception:
        pass
    return _fallback_segment(chunk)


def _merge_scene_ranges(ranges: list[dict[str, Any]], total_lines: int) -> list[dict[str, Any]]:
    if not ranges:
        return _fallback_segment([])
    ordered = sorted(ranges, key=lambda x: (int(x["panel_range"][0]), int(x["panel_range"][1])))
    merged: list[dict[str, Any]] = []
    for item in ordered:
        lo, hi = int(item["panel_range"][0]), int(item["panel_range"][1])
        lo = max(1, lo)
        hi = min(total_lines, max(lo, hi))
        if not merged:
            merged.append({"scene_id": 1, "panel_range": [lo, hi], "description": str(item.get("description") or "scene_1")})
            continue
        prev = merged[-1]
        if lo <= int(prev["panel_range"][1]) + 1:
            prev["panel_range"][1] = max(int(prev["panel_range"][1]), hi)
        else:
            merged.append(
                {
                    "scene_id": len(merged) + 1,
                    "panel_range": [lo, hi],
                    "description": str(item.get("description") or f"scene_{len(merged) + 1}"),
                }
            )
    # Fill any uncovered gaps deterministically.
    filled: list[dict[str, Any]] = []
    cursor = 1
    for item in merged:
        lo, hi = int(item["panel_range"][0]), int(item["panel_range"][1])
        if lo > cursor:
            filled.append({"scene_id": len(filled) + 1, "panel_range": [cursor, lo - 1], "description": f"scene_{len(filled) + 1}"})
        filled.append({"scene_id": len(filled) + 1, "panel_range": [lo, hi], "description": item["description"]})
        cursor = hi + 1
    if cursor <= total_lines:
        filled.append({"scene_id": len(filled) + 1, "panel_range": [cursor, total_lines], "description": f"scene_{len(filled) + 1}"})
    return filled


def segment_scenes(lines: list[SrtTimelineLine]) -> list[dict[str, Any]]:
    if not lines:
        return []
    if not settings.openai_dialogue_analysis_enabled or not settings.openai_api_key:
        return _fallback_segment(lines)

    total = len(lines)
    window = max(40, int(settings.scene_segment_window_size))
    overlap = max(0, min(window - 5, int(settings.scene_segment_overlap)))
    step = max(1, window - overlap)
    all_ranges: list[dict[str, Any]] = []
    for start in range(0, total, step):
        end = min(total, start + window)
        chunk = lines[start:end]
        if not chunk:
            continue
        chunk_ranges = _segment_chunk(chunk, chunk_start=start, expected_total=total)
        all_ranges.extend(chunk_ranges)
        if end >= total:
            break
    merged = _merge_scene_ranges(all_ranges, total_lines=total)
    if not merged:
        return _fallback_segment(lines)
    return merged

