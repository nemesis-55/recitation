from __future__ import annotations

import logging
from pathlib import Path

from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine, SrtTimelineLine
from app.services.audio.audio_mixer import mix_audio
from app.services.audio.character_engine import get_voice
from app.services.audio.dialogue_analyzer import analyze_srt_timeline
from app.services.audio.elevenlabs_sts import convert_speech_to_voice
from app.services.audio.music_engine import resolve_music_bed
from app.services.audio.speech_renderer import render_speech
from app.services.audio.timeline_builder import AudioEvent, build_cinematic_timeline, build_timeline
from app.services.audio.tts_elevenlabs import generate_tts
from app.utils.ffmpeg_runner import probe_duration_seconds, run_ffmpeg
from app.config import settings

logger = logging.getLogger(__name__)


def _to_script_line(item: SrtTimelineLine, panel_path: str) -> ScriptLine:
    return ScriptLine(
        panel_path=panel_path,
        narration=item.text,
        speaker=item.speaker,
        emotion=item.emotion,
        emotion_intensity=item.intensity,
    )


def _write_silence_segment(output_path: Path, duration_sec: float) -> None:
    dur = max(0.05, float(duration_sec))
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            f"{dur:.3f}",
            "-c:a",
            "libmp3lame",
            str(output_path),
        ],
        stage="audio_pipeline",
    )


def run_audio_pipeline(
    lines: list[SrtTimelineLine], audio_dir: Path, panel_paths: list[str]
) -> tuple[Path, list[AudioSegmentSchema], list[dict], dict]:
    if not panel_paths:
        raise ValueError("audio_pipeline requires at least one panel path")
    logger.info("audio_pipeline start lines=%s panel_paths=%s", len(lines), len(panel_paths))
    analyzed = analyze_srt_timeline(lines)
    voice_events: list[AudioEvent] = []
    # Keep narration + background music only (no SFX layer).
    sfx_events: list[AudioEvent] = []
    segments: list[AudioSegmentSchema] = []
    script_lines: list[ScriptLine] = []
    prev_voice_end = 0.0
    for idx, line in enumerate(analyzed):
        panel_path = panel_paths[min(idx, max(0, len(panel_paths) - 1))]
        sl = _to_script_line(line, panel_path=panel_path)
        sl.voice = get_voice(sl, idx)
        sl.rendered_text = render_speech(line.text, line.emotion, float(line.intensity))
        voice_path = audio_dir / f"line_{idx:03d}.mp3"
        raw_start = float(line.start_sec)
        # Never begin a line before the previous spoken line has ended.
        start = max(raw_start, prev_voice_end)
        slot_dur = max(0.05, float(line.end_sec - line.start_sec))
        if sl.rendered_text:
            generate_tts(
                text=sl.rendered_text,
                voice_id=sl.voice,
                emotion=sl.emotion,
                intensity=float(sl.emotion_intensity or 0.5),
                output_path=voice_path,
            )
            if settings.elevenlabs_sts_enabled and float(sl.emotion_intensity or 0.5) >= settings.elevenlabs_sts_intensity_threshold:
                sts_path = audio_dir / f"line_{idx:03d}_sts.mp3"
                convert_speech_to_voice(voice_path, sl.voice, sts_path)
                voice_path = sts_path
            voice_dur = max(0.05, probe_duration_seconds(voice_path))
            logger.info(
                "audio_pipeline line_done line_index=%s speaker=%s emotion=%s intensity=%.2f",
                idx,
                sl.speaker,
                sl.emotion,
                float(sl.emotion_intensity or 0.5),
            )
        else:
            _write_silence_segment(voice_path, slot_dur)
            voice_dur = slot_dur
            logger.info("audio_pipeline line_done line_index=%s mode=silence slot_dur=%.2f", idx, slot_dur)
        voice_events.append(AudioEvent(type="voice", file=str(voice_path), start=start, duration=voice_dur, line_index=idx))
        prev_voice_end = start + voice_dur
        segments.append(
            AudioSegmentSchema(
                line_index=idx,
                audio_path=str(voice_path),
                start_sec=start,
                end_sec=start + voice_dur,
                duration_sec=voice_dur,
                pause_sec=max(0.0, slot_dur - voice_dur),
                provider="elevenlabs",
                voice=sl.voice,
                rendered_text=sl.rendered_text,
            )
        )
        line.panel_path = panel_path
        line.performance_text = sl.rendered_text
        script_lines.append(sl)

    music_bed, music_src, music_reason = resolve_music_bed(script_lines, audio_dir)
    music_event = None
    if music_bed is not None:
        music_event = AudioEvent(type="music", file=str(music_bed), start=0.0, duration=0.0, line_index=-1)

    events = build_cinematic_timeline(voice_events=voice_events, sfx_events=sfx_events, music_event=music_event)
    narration_path = audio_dir / "narration.mp3"
    logger.info(
        "audio_pipeline mixer_begin voice_events=%s sfx_events=%s music_source=%s",
        len(voice_events),
        len(sfx_events),
        music_src,
    )
    mix_audio(events=events, output_path=narration_path, work_dir=audio_dir)
    logger.info("audio_pipeline mixer_done output=%s", narration_path)
    audio_meta = {
        "narration_music_source": music_src,
        "narration_music_reason": music_reason,
        "sfx_source": "disabled",
        "quality": "cinematic",
    }
    return narration_path, segments, build_timeline(events), audio_meta
