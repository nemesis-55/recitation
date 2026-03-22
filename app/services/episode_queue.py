from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.models.schemas import EpisodeRangeGenerateRequest, EpisodeRangeGenerateResponse, GenerateRequest
from app.routes.generate import generate_video
from app.services.manga_catalog import list_episodes
from app.utils.errors import PipelineError
from app.utils.ffmpeg_runner import run_ffmpeg

logger = logging.getLogger(__name__)


def _select_episode_range(episodes: list[dict], ep_from: int | None, ep_to: int | None) -> list[dict]:
    if not episodes:
        return []
    items = sorted(episodes, key=lambda e: int(e.get("episode_no") or 0))
    if ep_from is None and ep_to is None:
        return items
    start = ep_from if ep_from is not None else int(items[0].get("episode_no") or 0)
    end = ep_to if ep_to is not None else int(items[-1].get("episode_no") or 0)
    if end < start:
        start, end = end, start
    return [e for e in items if start <= int(e.get("episode_no") or 0) <= end]


def _select_episodes(episodes: list[dict], payload: EpisodeRangeGenerateRequest) -> tuple[list[dict], str]:
    items = sorted(episodes, key=lambda e: int(e.get("episode_no") or 0))
    if payload.select_all_episodes:
        return items, "all"
    chosen = [int(x) for x in (payload.episode_numbers or []) if int(x) >= 0]
    if chosen:
        wanted = set(chosen)
        return [e for e in items if int(e.get("episode_no") or 0) in wanted], "explicit_list"
    return _select_episode_range(items, payload.episode_from, payload.episode_to), "range"


def _has_panel_filters(payload: EpisodeRangeGenerateRequest) -> bool:
    return any(v is not None for v in (payload.page_from, payload.page_to, payload.panel_from, payload.panel_to))


def _run_root_from_report_path(report_path: str | None) -> Path | None:
    if not report_path:
        return None
    p = Path(report_path)
    if p.name != "job_report.json" or p.parent.name != "meta":
        return None
    return p.parent.parent


def _stitch_chunk_videos(video_paths: list[str], output_path: Path) -> None:
    list_file = output_path.parent / "chunk_concat.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text("\n".join([f"file '{Path(v).resolve().as_posix()}'" for v in video_paths]), encoding="utf-8")
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ],
        stage="episode_queue",
        timeout_sec=max(settings.stage_timeout_sec, 900),
    )


def _read_selected_panel_count(report_path: str | None) -> int | None:
    if not report_path:
        return None
    p = Path(report_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    stages = data.get("stages") if isinstance(data, dict) else None
    if not isinstance(stages, dict):
        return None
    panel_filter = stages.get("panel_filter")
    if isinstance(panel_filter, dict) and isinstance(panel_filter.get("selected_panels"), int):
        return int(panel_filter["selected_panels"])
    panel_limit = stages.get("panel_limit")
    if isinstance(panel_limit, dict) and isinstance(panel_limit.get("selected_panels"), int):
        return int(panel_limit["selected_panels"])
    panel_qa = stages.get("panel_qa")
    if isinstance(panel_qa, dict) and isinstance(panel_qa.get("count"), int):
        return int(panel_qa["count"])
    return None


def _generate_episode_with_auto_chunk(payload: EpisodeRangeGenerateRequest, viewer_url: str, ep_no: int, episode_slug: str | None) -> dict:
    chunk_size = max(1, int(settings.auto_chunk_max_panels))
    max_chunks = max(1, int(settings.auto_chunk_max_chunks))
    chunk_videos: list[str] = []
    chunk_run_roots: list[str] = []
    first_run_root: Path | None = None
    last_report_path: str | None = None
    cursor = 1
    for chunk_idx in range(max_chunks):
        req = GenerateRequest(
            pdf_path=viewer_url,
            srt_path=payload.srt_path,
            subtitles=payload.subtitles,
            target_duration_sec=payload.target_duration_sec,
            max_panels=None,
            page_from=None,
            page_to=None,
            panel_from=cursor,
            panel_to=cursor + chunk_size - 1,
            bgm_path=payload.bgm_path,
        )
        response = generate_video(req)
        if response.status == "failed" and response.error_code == "PANEL_RANGE_EMPTY":
            break
        if response.status != "completed":
            return {
                "episode_no": ep_no,
                "episode_slug": episode_slug,
                "viewer_url": viewer_url,
                "status": "failed",
                "video_path": response.video_path,
                "audio_path": response.audio_path,
                "error_code": response.error_code,
                "error": response.error,
                "report_path": response.report_path,
            }
        if response.video_path:
            chunk_videos.append(response.video_path)
        run_root = _run_root_from_report_path(response.report_path)
        if run_root is not None:
            chunk_run_roots.append(str(run_root))
            if first_run_root is None:
                first_run_root = run_root
        last_report_path = response.report_path
        selected_panels = _read_selected_panel_count(response.report_path)
        if selected_panels is not None and selected_panels < chunk_size:
            # Last chunk consumed fewer panels than requested; episode is complete.
            break
        cursor += chunk_size
    if not chunk_videos:
        return {
            "episode_no": ep_no,
            "episode_slug": episode_slug,
            "viewer_url": viewer_url,
            "status": "failed",
            "video_path": None,
            "audio_path": None,
            "error_code": "PANEL_RANGE_EMPTY",
            "error": "No panels found for this episode/chunk.",
            "report_path": None,
        }
    final_video = chunk_videos[0]
    complete_root: Path | None = None
    if first_run_root is not None:
        complete_root = first_run_root.parent / f"{first_run_root.name}_complete"
    if settings.auto_chunk_stitch and len(chunk_videos) > 1 and complete_root is not None:
        stitched = complete_root / "final" / "video_full.mp4"
        try:
            _stitch_chunk_videos(chunk_videos, stitched)
            final_video = str(stitched)
        except PipelineError as exc:
            return {
                "episode_no": ep_no,
                "episode_slug": episode_slug,
                "viewer_url": viewer_url,
                "status": "failed",
                "video_path": None,
                "audio_path": None,
                "error_code": exc.error_code,
                "error": exc.message,
                "report_path": None,
            }
    if complete_root is not None:
        meta_dir = complete_root / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "title_slug": payload.title_slug,
            "episode_no": ep_no,
            "episode_slug": episode_slug,
            "viewer_url": viewer_url,
            "chunk_size": chunk_size,
            "chunk_count": len(chunk_videos),
            "chunk_videos": chunk_videos,
            "chunk_run_roots": chunk_run_roots,
            "stitched_video": final_video,
            "stitched": bool(settings.auto_chunk_stitch and len(chunk_videos) > 1),
        }
        (meta_dir / "chunk_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "episode_no": ep_no,
        "episode_slug": episode_slug,
        "viewer_url": viewer_url,
        "status": "completed",
        "video_path": final_video,
        "audio_path": None,
        "error_code": None,
        "error": None,
        "report_path": last_report_path,
    }


def run_episode_range_sequential(payload: EpisodeRangeGenerateRequest) -> EpisodeRangeGenerateResponse:
    episodes = list_episodes(payload.title_slug)
    selected, mode = _select_episodes(episodes, payload)
    logger.info(
        "episode_queue enqueue title_slug=%s mode=%s requested_from=%s requested_to=%s selected=%s",
        payload.title_slug,
        mode,
        payload.episode_from,
        payload.episode_to,
        len(selected),
    )
    if not selected:
        return EpisodeRangeGenerateResponse(
            status="failed",
            title_slug=payload.title_slug,
            submitted=0,
            completed=0,
            failed=0,
            results=[
                {
                    "status": "failed",
                    "error_code": "EPISODES_NOT_FOUND",
                    "error": "No episodes matched your selection.",
                }
            ],
        )
    if _has_panel_filters(payload) and len(selected) != 1:
        return EpisodeRangeGenerateResponse(
            status="failed",
            title_slug=payload.title_slug,
            submitted=len(selected),
            completed=0,
            failed=len(selected),
            results=[
                {
                    "status": "failed",
                    "error_code": "PANEL_FILTER_SINGLE_EPISODE_ONLY",
                    "error": "Page/Panel filters are supported only when exactly one episode is selected.",
                }
            ],
        )
    results: list[dict] = []
    completed = 0
    failed = 0
    for idx, episode in enumerate(selected, start=1):
        viewer_url = str(episode.get("viewer_url") or "").strip()
        ep_no = int(episode.get("episode_no") or 0)
        logger.info(
            "episode_queue start title_slug=%s episode_no=%s progress=%s/%s",
            payload.title_slug,
            ep_no,
            idx,
            len(selected),
        )
        if settings.auto_chunk_enabled and not _has_panel_filters(payload) and payload.max_panels is None:
            result = _generate_episode_with_auto_chunk(payload, viewer_url, ep_no, episode.get("episode_slug"))
        else:
            req = GenerateRequest(
                pdf_path=viewer_url,
                srt_path=payload.srt_path,
                subtitles=payload.subtitles,
                target_duration_sec=payload.target_duration_sec,
                max_panels=payload.max_panels,
                page_from=payload.page_from,
                page_to=payload.page_to,
                panel_from=payload.panel_from,
                panel_to=payload.panel_to,
                bgm_path=payload.bgm_path,
            )
            response = generate_video(req)
            result = {
                "episode_no": ep_no,
                "episode_slug": episode.get("episode_slug"),
                "viewer_url": viewer_url,
                "status": response.status,
                "video_path": response.video_path,
                "audio_path": response.audio_path,
                "error_code": response.error_code,
                "error": response.error,
                "report_path": response.report_path,
            }
        results.append(result)
        if result["status"] == "completed":
            completed += 1
            logger.info("episode_queue completed title_slug=%s episode_no=%s", payload.title_slug, ep_no)
        else:
            failed += 1
            logger.info(
                "episode_queue failed title_slug=%s episode_no=%s error_code=%s",
                payload.title_slug,
                ep_no,
                result.get("error_code"),
            )

    status = "completed"
    if failed and completed:
        status = "partial"
    elif failed and not completed:
        status = "failed"
    return EpisodeRangeGenerateResponse(
        status=status,
        title_slug=payload.title_slug,
        submitted=len(selected),
        completed=completed,
        failed=failed,
        results=results,
    )

