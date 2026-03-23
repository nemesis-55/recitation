from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter

from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine, SrtTimelineLine
from app.services.audio.audio_mixer import mix_audio
from app.services.audio.character_engine import get_character_profile, get_voice
from app.services.audio.dialogue_analyzer import analyze_srt_timeline
from app.services.audio.episode_state import EpisodeState
from app.services.audio.scene_processor import process_scene
from app.services.audio.scene_segmenter import segment_scenes
from app.services.audio.scene_analyzer import analyze_scene
from app.services.audio.music_engine import resolve_music_bed  # compatibility for tests/older patch points
from app.services.audio.tts_elevenlabs import generate_tts  # compatibility for tests/older patch points
from app.utils.ffmpeg_runner import probe_duration_seconds, run_ffmpeg  # probe kept for test patch points
from app.utils.pipeline_debug import log_pipeline_debug
from app.config import settings
from app.services.audio.emotion_constants import ALLOWED_EMOTIONS

logger = logging.getLogger(__name__)


def _effective_crossfade_sec(scene_paths: list[str], requested: float) -> float:
    """Cap crossfade so each scene file is long enough for FFmpeg acrossfade."""
    if requested <= 0 or len(scene_paths) < 2:
        return 0.0
    req = min(0.5, max(0.0, float(requested)))
    durs: list[float] = []
    for p in scene_paths:
        try:
            durs.append(float(probe_duration_seconds(Path(p))))
        except Exception:
            durs.append(2.0)
    cap = min(durs) * 0.35
    return max(0.0, min(req, cap))


def _concat_scene_narration_files(
    scene_audio_files: list[str],
    narration_path: Path,
    crossfade_requested: float,
) -> float:
    """
    Merge per-scene narration MP3s. Returns effective crossfade duration in seconds (for timeline offsets).
    """
    paths = [str(Path(p).resolve()) for p in scene_audio_files]
    if len(paths) == 1:
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_bytes(Path(paths[0]).read_bytes())
        return 0.0
    d_eff = _effective_crossfade_sec(paths, crossfade_requested)
    narration_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = narration_path.parent / "scenes_concat.txt"
    concat_file.write_text("\n".join([f"file '{p}'" for p in paths]), encoding="utf-8")
    if d_eff <= 1e-9:
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(narration_path),
            ],
            stage="audio_pipeline",
        )
        return 0.0
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd.extend(["-i", p])
    fc_parts: list[str] = []
    prev = "[0:a]"
    for i in range(1, len(paths)):
        nxt = f"[{i}:a]"
        out = f"xf{i}" if i < len(paths) - 1 else "aout"
        fc_parts.append(f"{prev}{nxt}acrossfade=d={d_eff:.4f}:c1=tri:c2=tri[{out}]")
        prev = f"[{out}]"
    filter_complex = ";".join(fc_parts)
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(narration_path),
        ]
    )
    try:
        run_ffmpeg(cmd, stage="audio_pipeline")
        return d_eff
    except Exception as exc:
        logger.warning("scene audio crossfade failed (%s); using concat demuxer", exc)
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(narration_path),
            ],
            stage="audio_pipeline",
        )
        return 0.0


def _to_script_line(item: SrtTimelineLine, panel_path: str) -> ScriptLine:
    return ScriptLine(
        panel_path=panel_path,
        narration=item.text,
        speaker=item.speaker,
        emotion=item.emotion,
        emotion_intensity=item.intensity,
    )


def run_audio_pipeline(
    lines: list[SrtTimelineLine], audio_dir: Path, panel_paths: list[str]
) -> tuple[Path, list[AudioSegmentSchema], list[dict], dict]:
    if not panel_paths:
        raise ValueError("audio_pipeline requires at least one panel path")
    logger.info("audio_pipeline start lines=%s panel_paths=%s", len(lines), len(panel_paths))
    analyzed = analyze_srt_timeline(lines)
    scene_meta = analyze_scene(analyzed)
    if settings.audio_panel_wise_mode:
        # Panel-wise mode keeps OCR->panel->audio mapping deterministic and
        # avoids scene concat truncation by mixing the episode as one timeline.
        scenes = [
            {
                "scene_id": 1,
                "panel_range": [1, len(analyzed)],
                "scene_type": str(scene_meta.get("scene_type", "neutral")),
                "scene_emotion": str(scene_meta.get("scene_emotion", "neutral")),
                "description": "panel_wise_master_mix",
            }
        ]
    else:
        scenes = segment_scenes(analyzed)
    episode_state = EpisodeState()

    # Assign stable character voices once per episode.
    for idx, line in enumerate(analyzed):
        panel_path = panel_paths[min(idx, max(0, len(panel_paths) - 1))]
        sl = _to_script_line(line, panel_path=panel_path)
        v = get_voice(sl, idx)
        p = get_character_profile(sl, idx)
        episode_state.remember_character(sl.speaker, v, p)

    def _derive_scene_type(chunk: list[SrtTimelineLine]) -> str:
        emotions = [str(ln.emotion or "neutral").lower() for ln in chunk if (ln.text or "").strip()]
        if not emotions:
            return "neutral"
        counts = Counter(emotions)
        emo = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        if emo in {"angry", "urgent", "frustrated"}:
            return "fight"
        if emo in {
            "sad",
            "fear",
            "surprised",
            "confused",
            "hopeful",
            "resigned",
            "pain",
            "concerned",
            "worried",
            "weak",
            "nostalgic",
            "reassuring",
            "regretful",
            "apologetic",
            "serious",
            "desperate",
            "defensive",
        }:
            return "emotional"
        return "neutral"

    def _derive_scene_emotion(chunk: list[SrtTimelineLine]) -> str:
        emotions = [str(ln.emotion or "neutral").lower() for ln in chunk if (ln.text or "").strip()]
        if not emotions:
            return "neutral"
        counts = Counter(emotions)
        emo = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        return emo if emo in ALLOWED_EMOTIONS else "neutral"

    def _scene_input(scene: dict) -> tuple[dict, list[SrtTimelineLine], list[str], Path, float, EpisodeState, object, object, object, object]:
        lo, hi = int(scene["panel_range"][0]), int(scene["panel_range"][1])
        lo = max(1, lo)
        hi = min(len(analyzed), max(lo, hi))
        chunk = [analyzed[i - 1] for i in range(lo, hi + 1)]
        paths = [panel_paths[min(i - 1, len(panel_paths) - 1)] for i in range(lo, hi + 1)]
        scene = dict(scene)
        scene_type = str(scene.get("scene_type", "")).strip().lower()
        if scene_type not in {"fight", "emotional", "neutral"}:
            scene_type = _derive_scene_type(chunk)
        scene_emotion = str(scene.get("scene_emotion", "")).strip().lower()
        if scene_emotion not in ALLOWED_EMOTIONS:
            scene_emotion = _derive_scene_emotion(chunk)
        scene["scene_type"] = scene_type
        scene["scene_emotion"] = scene_emotion
        scene_dir = audio_dir / f"scene_{int(scene['scene_id']):03d}"
        scene_dir.mkdir(parents=True, exist_ok=True)
        scene_start = float(chunk[0].start_sec) if chunk else 0.0
        return scene, chunk, paths, scene_dir, scene_start, episode_state, generate_tts, mix_audio, resolve_music_bed, probe_duration_seconds

    scene_inputs = [_scene_input(scene) for scene in scenes]
    max_workers = max(1, min(4, len(scene_inputs)))
    if settings.audio_panel_wise_mode:
        max_workers = 1
    if max_workers == 1:
        scene_results = [process_scene(*inp) for inp in scene_inputs]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            scene_results = list(pool.map(lambda args: process_scene(*args), scene_inputs))

    scene_results.sort(key=lambda x: int(x.get("scene_id", 0)))
    log_pipeline_debug(
        run_id="audio_pipeline",
        hypothesis_id="scene_results",
        location="audio_pipeline.py:run_audio_pipeline",
        message="Scene results summary",
        data={
            "scene_count": len(scene_results),
            "scene_audio_files": [str(sr.get("audio")) for sr in scene_results],
            "scene_declared_durations": [float(sr.get("duration", 0.0)) for sr in scene_results],
        },
    )
    scene_audio_files = [str(Path(sr["audio"]).resolve()) for sr in scene_results]
    narration_path = audio_dir / "narration.mp3"
    scene_join_cf = _concat_scene_narration_files(
        scene_audio_files,
        narration_path,
        float(getattr(settings, "audio_scene_crossfade_sec", 0) or 0),
    )

    # Flatten scene timelines into episode timeline using cumulative offsets.
    flattened_timeline: list[dict] = []
    flattened_segments: list[AudioSegmentSchema] = []
    scene_offset = 0.0
    line_cursor = 0
    for i, sr in enumerate(scene_results):
        for e in sr.get("timeline", []):
            flattened_timeline.append(
                {
                    "type": e.get("type"),
                    "file": e.get("file"),
                    "start": round(float(e.get("start", 0.0)) + scene_offset, 3),
                    "duration": round(float(e.get("duration", 0.0)), 3),
                    "line_index": int(e.get("line_index", -1)) + line_cursor,
                }
            )
        for seg in sr.get("segments", []):
            flattened_segments.append(
                AudioSegmentSchema(
                    line_index=int(seg.line_index) + line_cursor,
                    audio_path=seg.audio_path,
                    start_sec=float(seg.start_sec) + scene_offset,
                    end_sec=float(seg.end_sec) + scene_offset,
                    duration_sec=float(seg.duration_sec),
                    pause_sec=float(seg.pause_sec),
                    provider=seg.provider,
                    voice=seg.voice,
                    rendered_text=seg.rendered_text,
                )
            )
        scene_duration = float(sr.get("duration", 0.0))
        scene_audio_file = sr.get("audio")
        if scene_audio_file:
            try:
                scene_duration = max(scene_duration, float(probe_duration_seconds(Path(str(scene_audio_file)))))
            except Exception:
                pass
        scene_offset += scene_duration
        if i < len(scene_results) - 1 and scene_join_cf > 1e-9:
            scene_offset -= scene_join_cf
        line_cursor += len(sr.get("segments", []))

    # Subtitles / timeline: what TTS actually spoke (post render_speech + optional bridge).
    for seg in flattened_segments:
        li = int(seg.line_index)
        if 0 <= li < len(lines):
            rt = (seg.rendered_text or "").strip()
            lines[li].performance_text = rt if rt else None

    bed_sources = [str(sr.get("music_source") or "") for sr in scene_results]
    primary_bed = next((s for s in bed_sources if s in ("bgm_library", "elevenlabs", "bgm_default")), None)
    audio_meta = {
        "narration_music_source": primary_bed if primary_bed else "none",
        "narration_music_reason": "scene_processing",
        "scene_join_crossfade_sec": round(float(scene_join_cf), 4),
        "sfx_source": "enabled" if settings.elevenlabs_sfx_enabled else "disabled",
        "quality": "cinematic",
        "audio_mode": "panel_wise_single_mix" if settings.audio_panel_wise_mode else "scene_chunked",
        "scene_type": str(scene_meta.get("scene_type", "neutral")),
        "scene_emotion": str(scene_meta.get("scene_emotion", "neutral")),
        "characters": list(episode_state.characters.values()),
        "scenes": [{"scene_id": int(s.get("scene_id", 0)), "panel_range": s.get("panel_range")} for s in scenes],
    }
    return narration_path, flattened_segments, flattened_timeline, audio_meta
