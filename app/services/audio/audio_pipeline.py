from __future__ import annotations

import json
import logging
import time
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
from app.config import settings

logger = logging.getLogger(__name__)
_DEBUG_LOG_PATH = Path("/Users/nemesis/Desktop/project/manga_recitation/.cursor/debug-4a522c.log")


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "4a522c",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


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
        if emo == "angry":
            return "fight"
        if emo in {"sad", "fear", "surprised", "confused"}:
            return "emotional"
        return "neutral"

    def _derive_scene_emotion(chunk: list[SrtTimelineLine]) -> str:
        emotions = [str(ln.emotion or "neutral").lower() for ln in chunk if (ln.text or "").strip()]
        if not emotions:
            return "neutral"
        counts = Counter(emotions)
        emo = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        return emo if emo in {"angry", "fear", "sad", "happy", "neutral", "surprised", "curious", "confused"} else "neutral"

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
        if scene_emotion not in {"angry", "fear", "sad", "happy", "neutral", "surprised", "curious", "confused"}:
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
    # region agent log
    _debug_log(
        run_id="pre-fix-1",
        hypothesis_id="H4",
        location="audio_pipeline.py:run_audio_pipeline",
        message="Scene results summary",
        data={
            "scene_count": len(scene_results),
            "scene_audio_files": [str(sr.get("audio")) for sr in scene_results],
            "scene_declared_durations": [float(sr.get("duration", 0.0)) for sr in scene_results],
        },
    )
    # endregion
    scene_audio_files = [str(Path(sr["audio"]).resolve()) for sr in scene_results]
    narration_path = audio_dir / "narration.mp3"
    if len(scene_audio_files) == 1:
        narration_path.write_bytes(Path(scene_audio_files[0]).read_bytes())
    else:
        concat_file = audio_dir / "scenes_concat.txt"
        concat_file.write_text("\n".join([f"file '{p}'" for p in scene_audio_files]), encoding="utf-8")
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
                str(narration_path),
            ],
            stage="audio_pipeline",
        )

    # Flatten scene timelines into episode timeline using cumulative offsets.
    flattened_timeline: list[dict] = []
    flattened_segments: list[AudioSegmentSchema] = []
    scene_offset = 0.0
    line_cursor = 0
    for sr in scene_results:
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
        line_cursor += len(sr.get("segments", []))

    audio_meta = {
        "narration_music_source": "scene_level",
        "narration_music_reason": "scene_processing",
        "sfx_source": "enabled" if settings.elevenlabs_sfx_enabled else "disabled",
        "quality": "cinematic",
        "audio_mode": "panel_wise_single_mix" if settings.audio_panel_wise_mode else "scene_chunked",
        "scene_type": str(scene_meta.get("scene_type", "neutral")),
        "scene_emotion": str(scene_meta.get("scene_emotion", "neutral")),
        "characters": list(episode_state.characters.values()),
        "scenes": [{"scene_id": int(s.get("scene_id", 0)), "panel_range": s.get("panel_range")} for s in scenes],
    }
    return narration_path, flattened_segments, flattened_timeline, audio_meta
