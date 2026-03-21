from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import GenerateRequest, GenerateResponse
from app.services.narrator import generate_voice
from app.services.ocr_engine import extract_text_batch
from app.services.panel_animator import animate_panel
from app.services.panel_extractor import extract_panels
from app.services.pdf_loader import load_pdf
from app.services.preflight import run_preflight, validate_page_resolution
from app.services.quality_checker import check_video
from app.services.script_cleaner import clean_script
from app.services.subtitle_generator import generate_subtitles
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

        if payload.max_panels is not None:
            original_count = len(panels)
            panels = panels[: payload.max_panels]
            report["stages"]["panel_limit"] = {
                "requested_max_panels": payload.max_panels,
                "original_panels": original_count,
                "selected_panels": len(panels),
            }

        with StageTimer(logger, "ocr_engine"):
            stage_start = time.time()
            qa_panels = _validate_panel_assets(panels)
            report["stages"]["panel_qa"] = qa_panels
            log_event(logger, "panel_qa", "done", **qa_panels)
            if qa_panels["missing_count"] > 0:
                raise PipelineError(
                    stage="panel_qa",
                    message=f"Missing panel files detected before OCR (count={qa_panels['missing_count']})",
                    error_code="PANEL_FILES_MISSING",
                )
            if qa_panels["unreadable_count"] > 0:
                raise PipelineError(
                    stage="panel_qa",
                    message=f"Unreadable panel files detected before OCR (count={qa_panels['unreadable_count']})",
                    error_code="PANEL_FILES_UNREADABLE",
                )
            api_start = time.time()
            ocr = extract_text_batch(panels)
            _enforce_stage_timeout("ocr_engine", stage_start)
            report["stages"]["ocr_engine"] = {
                "items": len(ocr),
                "model": settings.openai_model,
                "elapsed_ms": round((time.time() - api_start) * 1000),
            }

        with StageTimer(logger, "script_cleaner"):
            stage_start = time.time()
            api_start = time.time()
            script = clean_script(ocr)
            _enforce_stage_timeout("script_cleaner", stage_start)
            report["stages"]["script_cleaner"] = {
                "lines": len(script),
                "provider": "openai",
                "model": settings.openai_model,
                "elapsed_ms": round((time.time() - api_start) * 1000),
            }
            report["artifacts"] = report.get("artifacts", {})
            report["artifacts"]["openai_narration"] = [
                {
                    "panel_path": line.panel_path,
                    "speaker": line.speaker,
                    "gender": line.gender,
                    "voice": line.voice,
                    "emotion": line.emotion,
                    "narration": line.narration,
                }
                for line in script
            ]

        with StageTimer(logger, "narrator"):
            stage_start = time.time()
            api_start = time.time()
            narration_path, audio_segments = generate_voice(script, dirs["audio"])
            _enforce_stage_timeout("narrator", stage_start)
            report["stages"]["narrator"] = {
                "segments": len(audio_segments),
                "provider": settings.tts_provider,
                "openai_tts_model": settings.openai_tts_model,
                "elapsed_ms": round((time.time() - api_start) * 1000),
            }

        with StageTimer(logger, "timeline_builder"):
            stage_start = time.time()
            timeline = build_timeline(panels, script, audio_segments)
            _enforce_stage_timeout("timeline_builder", stage_start)
            report["stages"]["timeline_builder"] = {"entries": len(timeline)}
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

        with StageTimer(logger, "video_editor"):
            stage_start = time.time()
            final_path = dirs["final"] / "video.mp4"
            final_video = assemble_video(
                clips=clips,
                narration_path=narration_path,
                output_path=final_path,
                subtitles_path=subtitles_path,
                bgm_path=payload.bgm_path or settings.bgm_default_path,
            )
            _enforce_stage_timeout("video_editor", stage_start)
            report["stages"]["video_editor"] = {"video_path": str(final_video)}

        with StageTimer(logger, "quality_checker"):
            stage_start = time.time()
            qc = check_video(final_video)
            _enforce_stage_timeout("quality_checker", stage_start)
            report["stages"]["quality_checker"] = qc.model_dump()

        report["elapsed_sec"] = round(time.time() - start, 3)
        report_path = dirs["meta"] / "job_report.json"
        write_json(report_path, report)
        return GenerateResponse(status="completed", video_path=str(final_video), report_path=str(report_path))
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
