from __future__ import annotations

from app.config import settings
from app.models.schemas import AudioSegment, PanelAsset, ScriptLine, SrtTimelineLine, TimelineEntry


def _clamp_duration(duration: float) -> float:
    return max(settings.min_panel_duration_sec, min(settings.max_panel_duration_sec, duration))


def build_timeline(panels: list[PanelAsset], script: list[ScriptLine], audio: list[AudioSegment]) -> list[TimelineEntry]:
    if not panels:
        return []

    if script:
        lines = script
    elif settings.subtitle_strict_from_script:
        lines = [ScriptLine(panel_path=panels[i].image_path, narration="", emotion="neutral") for i in range(len(panels))]
    else:
        lines = [ScriptLine(panel_path=panels[i].image_path, narration="...", emotion="neutral") for i in range(len(panels))]
    out: list[TimelineEntry] = []
    cursor = 0.0
    lines_by_panel_path: dict[str, list[ScriptLine]] = {}
    for line in lines:
        lines_by_panel_path.setdefault(line.panel_path, []).append(line)
    panel_audio_duration_by_path: dict[str, float] = {}
    for seg in audio:
        if 0 <= seg.line_index < len(lines):
            line = lines[seg.line_index]
            panel_audio_duration_by_path[line.panel_path] = panel_audio_duration_by_path.get(line.panel_path, 0.0) + max(
                0.0, seg.duration_sec + seg.pause_sec
            )
    has_audio_timing = len(panel_audio_duration_by_path) > 0

    for panel in panels:
        line_group = lines_by_panel_path.get(panel.image_path, [])
        if line_group:
            narration = " ".join([(ln.narration or "").strip() for ln in line_group if (ln.narration or "").strip()]).strip()
            if not narration:
                narration = ""
        else:
            narration = "" if settings.subtitle_strict_from_script else "..."
        panel_audio_duration = panel_audio_duration_by_path.get(panel.image_path)
        if panel_audio_duration is not None:
            # When audio exists, use it as source-of-truth for panel duration.
            dur = max(0.1, panel_audio_duration)
        else:
            # Keep textless/unvoiced panels visible long enough; do not skip too fast.
            dur = max(settings.min_panel_duration_sec, 2.0)
        start = cursor
        end = start + dur
        out.append(
            TimelineEntry(
                panel_path=panel.image_path,
                narration=narration,
                start_sec=start,
                end_sec=end,
                duration_sec=dur,
            )
        )
        cursor = end

    total = out[-1].end_sec if out else 0
    if total < settings.min_video_duration_sec and out and not has_audio_timing:
        multiplier = settings.min_video_duration_sec / total
        cursor = 0.0
        for item in out:
            item.duration_sec = _clamp_duration(item.duration_sec * multiplier)
            item.start_sec = cursor
            item.end_sec = cursor + item.duration_sec
            cursor = item.end_sec

    if has_audio_timing:
        return out

    # Trim if beyond max duration.
    filtered: list[TimelineEntry] = []
    for item in out:
        if item.start_sec >= settings.max_video_duration_sec:
            break
        item.end_sec = min(item.end_sec, float(settings.max_video_duration_sec))
        item.duration_sec = item.end_sec - item.start_sec
        filtered.append(item)
    return filtered


def build_timeline_from_srt(panels: list[PanelAsset], srt_lines: list[SrtTimelineLine]) -> list[TimelineEntry]:
    if not panels or not srt_lines:
        return []
    count = min(len(panels), len(srt_lines))
    out: list[TimelineEntry] = []
    for i in range(count):
        panel = panels[i]
        line = srt_lines[i]
        start = max(0.0, float(line.start_sec))
        end = max(start + 0.05, float(line.end_sec))
        out.append(
            TimelineEntry(
                panel_path=panel.image_path,
                narration=line.text,
                start_sec=start,
                end_sec=end,
                duration_sec=end - start,
            )
        )
    return out
