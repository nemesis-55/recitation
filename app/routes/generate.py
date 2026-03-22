from __future__ import annotations
import logging
import time
from pathlib import Path

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import GenerateRequest, GenerateResponse, ScriptLine, SrtTimelineLine
from app.services.narrator import generate_voice
from app.services.ocr_engine import extract_text_batch
from app.services.panel_animator import animate_panel
from app.services.panel_extractor import extract_panels
from app.services.pdf_loader import load_pdf
from app.services.preflight import run_preflight, validate_page_resolution
from app.services.quality_checker import check_video
from app.services.subtitle_generator import generate_subtitles, load_srt_timeline
from app.services.timeline_builder import build_timeline
from app.services.video_editor import assemble_video
from app.services.webtoon_loader import is_webtoon_url, load_webtoon_panels
from app.utils.errors import PipelineError
from app.utils.io_utils import create_run_dirs, derive_run_path_from_source, write_json
from app.utils.logging_utils import StageTimer, log_event

router = APIRouter()
logger = logging.getLogger(__name__)


def _enforce_stage_timeout(stage: str, stage_started_at: float) -> None:
    elapsed = time.time() - stage_started_at
    if elapsed > settings.stage_timeout_sec:
        raise PipelineError(stage=stage, message=f"Stage timeout after {elapsed:.2f}s", error_code="STAGE_TIMEOUT")


def _validate_panel_assets(panels) -> dict:
    missing: list[str] = []
    unreadable: list[str] = []
    total_bytes = 0
    for panel in panels:
        path = Path(panel.image_path)
        if not path.exists():
            missing.append(str(path))
            continue
        try:
            size = path.stat().st_size
            total_bytes += size
            if size <= 0:
                unreadable.append(f"{path} (0 bytes)")
        except Exception:
            unreadable.append(f"{path} (stat failed)")
    return {
        "count": len(panels),
        "missing_count": len(missing),
        "unreadable_count": len(unreadable),
        "total_bytes": total_bytes,
        "missing_examples": missing[:5],
        "unreadable_examples": unreadable[:5],
    }


def _build_srt_lines_from_ocr(ocr_items, fallback_duration: float = 2.0) -> list[SrtTimelineLine]:
    lines: list[SrtTimelineLine] = []
    cursor = 0.0
    for idx, item in enumerate(ocr_items, start=1):
        text = (item.text or "").strip()
        # Keep silent slots for low-confidence OCR instead of forcing filler speech.
        if bool(getattr(item, "low_confidence", False)) and len(text) <= 16:
            text = ""
        # Simple duration heuristic for auto-generated subtitle timing.
        dur = max(0.8, min(8.0, max(fallback_duration, len(text) * 0.055)))
        lines.append(
            SrtTimelineLine(
                index=idx,
                start_sec=round(cursor, 3),
                end_sec=round(cursor + dur, 3),
                text=text,
            )
        )
        cursor += dur
    return lines


def _normalize_range(start: int | None, end: int | None) -> tuple[int, int] | None:
    if start is None and end is None:
        return None
    lo = start if start is not None else end
    hi = end if end is not None else start
    if lo is None or hi is None:
        return None
    if hi < lo:
        lo, hi = hi, lo
    return int(lo), int(hi)


def _apply_panel_ranges(panels, payload: GenerateRequest) -> tuple[list, dict]:
    out = panels
    page_range = _normalize_range(payload.page_from, payload.page_to)
    panel_range = _normalize_range(payload.panel_from, payload.panel_to)
    if page_range:
        out = [p for p in out if page_range[0] <= int(p.page_index) <= page_range[1]]
    if panel_range:
        out = [p for p in out if panel_range[0] <= int(p.panel_index) <= panel_range[1]]
    meta = {
        "requested_page_range": [page_range[0], page_range[1]] if page_range else None,
        "requested_panel_range": [panel_range[0], panel_range[1]] if panel_range else None,
        "selected_panels": len(out),
    }
    return out, meta


@router.post("/generate", response_model=GenerateResponse)
def generate_video(payload: GenerateRequest) -> GenerateResponse:
    dirs = None
    report: dict = {"input": payload.model_dump(), "stages": {}, "warnings": []}
    try:
        start = time.time()
        derived_run_path = derive_run_path_from_source(payload.pdf_path)
        dirs = create_run_dirs(job_id=derived_run_path)

        with StageTimer(logger, "preflight"):
            stage_start = time.time()
            run_preflight(payload.pdf_path)
            _enforce_stage_timeout("preflight", stage_start)
            report["stages"]["preflight"] = {"ok": True}

        if is_webtoon_url(payload.pdf_path):
            with StageTimer(logger, "webtoon_loader"):
                stage_start = time.time()
                panels = load_webtoon_panels(payload.pdf_path, dirs["panels"])
                _enforce_stage_timeout("webtoon_loader", stage_start)
                report["stages"]["webtoon_loader"] = {"panels": len(panels), "source": "webtoon_url"}
        else:
            with StageTimer(logger, "pdf_loader"):
                stage_start = time.time()
                pages = load_pdf(payload.pdf_path, dirs["pages"])
                validate_page_resolution(pages)
                _enforce_stage_timeout("pdf_loader", stage_start)
                report["stages"]["pdf_loader"] = {"pages": len(pages)}

            with StageTimer(logger, "panel_extractor"):
                stage_start = time.time()
                panels = []
                for p in pages:
                    panels.extend(extract_panels(p, dirs["panels"]))
                _enforce_stage_timeout("panel_extractor", stage_start)
                report["stages"]["panel_extractor"] = {"panels": len(panels)}

        if any(v is not None for v in (payload.page_from, payload.page_to, payload.panel_from, payload.panel_to)):
            original_count = len(panels)
            panels, filter_meta = _apply_panel_ranges(panels, payload)
            report["stages"]["panel_filter"] = {
                "original_panels": original_count,
                **filter_meta,
            }
            if not panels:
                raise PipelineError(
                    stage="panel_filter",
                    message="No panels matched the requested page/panel range.",
                    error_code="PANEL_RANGE_EMPTY",
                )

        if payload.max_panels is not None:
            original_count = len(panels)
            panels = panels[: payload.max_panels]
            report["stages"]["panel_limit"] = {
                "requested_max_panels": payload.max_panels,
                "original_panels": original_count,
                "selected_panels": len(panels),
            }

        with StageTimer(logger, "srt_loader"):
            stage_start = time.time()
            qa_panels = _validate_panel_assets(panels)
            report["stages"]["panel_qa"] = qa_panels
            log_event(logger, "panel_qa", "done", **qa_panels)
            if qa_panels["missing_count"] > 0:
                raise PipelineError(
                    stage="panel_qa",
                    message=f"Missing panel files detected before SRT stage (count={qa_panels['missing_count']})",
                    error_code="PANEL_FILES_MISSING",
                )
            if qa_panels["unreadable_count"] > 0:
                raise PipelineError(
                    stage="panel_qa",
                    message=f"Unreadable panel files detected before SRT stage (count={qa_panels['unreadable_count']})",
                    error_code="PANEL_FILES_UNREADABLE",
                )
            if payload.srt_path:
                srt_lines = load_srt_timeline(payload.srt_path)
                if len(srt_lines) > len(panels):
                    srt_lines = srt_lines[: len(panels)]
                report["stages"]["srt_loader"] = {"entries": len(srt_lines), "path": payload.srt_path, "source": "provided"}
                logger.info("srt_loader source=provided entries=%s path=%s", len(srt_lines), payload.srt_path)
            else:
                # Backward-compatible path: auto-generate SRT timeline from OCR.
                ocr = extract_text_batch(panels)
                srt_lines = _build_srt_lines_from_ocr(ocr, fallback_duration=max(1.2, settings.min_panel_duration_sec))
                if len(srt_lines) > len(panels):
                    srt_lines = srt_lines[: len(panels)]
                report["stages"]["srt_loader"] = {"entries": len(srt_lines), "path": None, "source": "auto_generated_from_ocr"}
                report["warnings"].append("srt_path not provided: generated subtitle timeline from OCR.")
                logger.info("srt_loader source=auto_generated_from_ocr entries=%s", len(srt_lines))
            _enforce_stage_timeout("srt_loader", stage_start)
            report["artifacts"] = report.get("artifacts", {})

        with StageTimer(logger, "narrator"):
            stage_start = time.time()
            api_start = time.time()
            panel_paths = [p.image_path for p in panels]
            narration_path, audio_segments, audio_timeline, audio_meta = generate_voice(srt_lines, panel_paths, dirs["audio"])
            _enforce_stage_timeout("narrator", stage_start)
            report["stages"]["narrator"] = {
                "segments": len(audio_segments),
                "provider": settings.tts_provider,
                "provider_order": settings.tts_provider_order,
                "elevenlabs_tts_model": settings.elevenlabs_tts_model,
                "elapsed_ms": round((time.time() - api_start) * 1000),
                **audio_meta,
            }
            report["artifacts"]["srt_analysis"] = [line.model_dump() for line in srt_lines]
            report["artifacts"]["audio_event_timeline"] = audio_timeline
            report["artifacts"]["audio_timeline"] = [seg.model_dump() for seg in audio_segments]
            write_json(dirs["meta"] / "audio_timeline.json", [seg.model_dump() for seg in audio_segments])
            logger.info(
                "narrator done segments=%s event_timeline=%s quality=%s",
                len(audio_segments),
                len(audio_timeline),
                audio_meta.get("quality", "cinematic"),
            )

        with StageTimer(logger, "timeline_builder"):
            stage_start = time.time()
            script_lines = [
                ScriptLine(
                    panel_path=s.panel_path or panels[min(i, len(panels) - 1)].image_path,
                    narration=(s.performance_text or s.text or "").strip(),
                    speaker=s.speaker,
                    emotion=s.emotion,
                    emotion_intensity=s.intensity,
                )
                for i, s in enumerate(srt_lines[: len(panels)])
            ]
            # Use generated audio segments as timing source-of-truth to prevent video racing ahead.
            timeline = build_timeline(panels, script_lines, audio_segments)
            _enforce_stage_timeout("timeline_builder", stage_start)
            report["stages"]["timeline_builder"] = {"entries": len(timeline), "source": "audio_segments"}
            write_json(dirs["meta"] / "timeline.json", [t.model_dump() for t in timeline])

        with StageTimer(logger, "panel_animator"):
            stage_start = time.time()
            clips = []
            for i, item in enumerate(timeline, start=1):
                out_clip = dirs["clips"] / f"clip_{i:03d}.mp4"
                animate_panel(item.panel_path, item.duration_sec, out_clip)
                item.clip_path = str(out_clip)
                clips.append(out_clip)
            _enforce_stage_timeout("panel_animator", stage_start)
            report["stages"]["panel_animator"] = {"clips": len(clips)}

        subtitles_path = None
        use_subtitles = payload.subtitles if payload.subtitles is not None else settings.enable_subtitles_default
        if use_subtitles:
            with StageTimer(logger, "subtitle_generator"):
                stage_start = time.time()
                subtitles_path, subtitle_entries = generate_subtitles(timeline, dirs["final"] / "subtitles.srt")
                _enforce_stage_timeout("subtitle_generator", stage_start)
                report["stages"]["subtitle_generator"] = {"entries": len(subtitle_entries)}
                if not subtitle_entries:
                    # Avoid ffmpeg failing on empty/invalid subtitle track input.
                    subtitles_path = None
                    report["warnings"].append("Subtitles disabled: no subtitle entries generated.")

        with StageTimer(logger, "video_editor"):
            stage_start = time.time()
            final_path = dirs["final"] / "video.mp4"
            video_bgm = payload.bgm_path or settings.bgm_default_path
            # Avoid doubling the same default BGM (already mixed under narration when source is bgm_default).
            if (
                not payload.bgm_path
                and audio_meta.get("narration_music_source") == "bgm_default"
                and settings.audio_bed_in_narration
            ):
                video_bgm = None
            final_video = assemble_video(
                clips=clips,
                narration_path=narration_path,
                output_path=final_path,
                subtitles_path=subtitles_path,
                bgm_path=video_bgm,
            )
            _enforce_stage_timeout("video_editor", stage_start)
            report["stages"]["video_editor"] = {"video_path": str(final_video)}

        with StageTimer(logger, "quality_checker"):
            stage_start = time.time()
            qc = check_video(final_video)
            _enforce_stage_timeout("quality_checker", stage_start)
            report["stages"]["quality_checker"] = qc.model_dump()

        if not settings.run_keep_intermediate_clips:
            for clip_path in clips:
                try:
                    clip_path.unlink(missing_ok=True)
                except OSError:
                    pass
            fin = dirs["final"]
            for name in ("merged.mp4", "concat.txt"):
                p = fin / name
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass

        report["elapsed_sec"] = round(time.time() - start, 3)
        report_path = dirs["meta"] / "job_report.json"
        write_json(report_path, report)
        return GenerateResponse(
            status="completed",
            video_path=str(final_video),
            audio_path=str(narration_path),
            quality=audio_meta.get("quality", "cinematic"),
            report_path=str(report_path),
        )
    except PipelineError as exc:
        report["failed"] = {
            "stage": exc.stage,
            "provider": exc.provider,
            "error_code": exc.error_code,
            "error": exc.message,
        }
        report_path = None
        if dirs is not None:
            report_path = dirs["meta"] / "job_report.json"
            write_json(report_path, report)
        log_event(logger, exc.stage, "failed", error_code=exc.error_code, provider=exc.provider, error=exc.message)
        return GenerateResponse(
            status="failed",
            stage=exc.stage,
            provider=exc.provider,
            error_code=exc.error_code,
            error=exc.message,
            report_path=str(report_path) if report_path else None,
        )
    except Exception as exc:
        report["failed"] = {
            "stage": "pipeline",
            "error_code": "UNHANDLED_ERROR",
            "error": str(exc),
        }
        report_path = None
        if dirs is not None:
            report_path = dirs["meta"] / "job_report.json"
            write_json(report_path, report)
        log_event(logger, "pipeline", "failed", error_code="UNHANDLED_ERROR", error=str(exc))
        return GenerateResponse(
            status="failed",
            stage="pipeline",
            error_code="UNHANDLED_ERROR",
            error=str(exc),
            report_path=str(report_path) if report_path else None,
        )
