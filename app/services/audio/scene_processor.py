from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine, SrtTimelineLine
from app.services.audio.audio_mixer import mix_audio
from app.services.audio.audio_rule_engine import resolve_audio_plan
from app.services.audio.character_engine import get_character_profile, get_voice
from app.services.audio.elevenlabs_engine import generate_sfx_event
from app.services.audio.pause_engine import create_silence_clip
from app.services.audio.pause_engine import pause_seconds
from app.services.audio.speech_renderer import render_speech
from app.services.audio.timeline_builder import AudioEvent, build_cinematic_timeline, build_timeline
from app.services.audio.tts_elevenlabs import generate_tts
from app.services.audio.music_engine import resolve_music_bed
from app.utils.ffmpeg_runner import probe_duration_seconds
from app.services.audio.episode_state import EpisodeState


def _to_script_line(item: SrtTimelineLine, panel_path: str) -> ScriptLine:
    return ScriptLine(
        panel_path=panel_path,
        narration=item.text,
        speaker=item.speaker,
        emotion=item.emotion,
        emotion_intensity=item.intensity,
    )


def process_scene(
    scene: dict[str, Any],
    scene_lines: list[SrtTimelineLine],
    scene_panel_paths: list[str],
    scene_audio_dir: Path,
    scene_start_sec: float,
    episode_state: EpisodeState,
    tts_func=generate_tts,
    mix_func=mix_audio,
    resolve_music_func=resolve_music_bed,
    probe_func=probe_duration_seconds,
) -> dict[str, Any]:
    voice_events: list[AudioEvent] = []
    sfx_events: list[AudioEvent] = []
    segments: list[AudioSegmentSchema] = []
    script_lines: list[ScriptLine] = []

    prev_voice_end = 0.0
    prev_pause = 0.0

    for idx, line in enumerate(scene_lines):
        panel_path = scene_panel_paths[min(idx, max(0, len(scene_panel_paths) - 1))]
        sl = _to_script_line(line, panel_path=panel_path)
        speaker_key = (sl.speaker or "unknown_1").strip().lower()
        sl.voice = episode_state.voice_map.get(speaker_key) or get_voice(sl, int(line.index))
        profile = get_character_profile(sl, int(line.index))
        plan = resolve_audio_plan(
            sl.narration,
            sl.emotion,
            float(sl.emotion_intensity or 0.5),
            str(scene.get("scene_type") or scene.get("description", "neutral")),
        )
        profile = {**profile, **plan.get("voice_settings", {})}
        sl.pause_sec = float(plan.get("pause", pause_seconds(sl.emotion, float(sl.emotion_intensity or 0.5))))
        sl.rendered_text = render_speech(
            sl.narration,
            sl.emotion,
            float(sl.emotion_intensity or 0.5),
            speech_mode=str(plan.get("speech_mode", "none")),
        )
        voice_path = scene_audio_dir / f"line_{idx:03d}.mp3"
        local_start = max(0.0, float(line.start_sec) - scene_start_sec)
        start = max(local_start, prev_voice_end + prev_pause)
        slot_dur = max(0.05, float(line.end_sec - line.start_sec))
        if sl.rendered_text:
            tts_func(
                text=sl.rendered_text,
                voice_id=sl.voice,
                emotion=sl.emotion,
                intensity=float(sl.emotion_intensity or 0.5),
                output_path=voice_path,
                profile=profile,
            )
            voice_dur = max(0.05, probe_func(voice_path))
        else:
            create_silence_clip(voice_path, slot_dur)
            voice_dur = slot_dur
        voice_events.append(AudioEvent(type="voice", file=str(voice_path), start=start, duration=voice_dur, line_index=idx))

        if settings.elevenlabs_sfx_enabled:
            for sfx_i, evt in enumerate(plan.get("sfx_plan", []), start=1):
                prompt = {
                    "impact": "Cinematic impact hit, tight transient and deep thump",
                    "thump": "Body thump impact, low-frequency floor hit",
                    "movement": "Fast cloth movement whoosh, short pass-by",
                    "light_breath": "Subtle anxious breath close mic",
                    "heavy_breath": "Heavy breath under stress close mic",
                }.get(str(evt), "")
                if not prompt:
                    continue
                sfx_path = scene_audio_dir / f"sfx_{idx:03d}_{sfx_i}.mp3"
                generate_sfx_event(prompt, 0.75, sfx_path)
                sfx_dur = max(0.05, probe_func(sfx_path))
                sfx_events.append(
                    AudioEvent(
                        type="sfx",
                        file=str(sfx_path),
                        start=max(0.0, start + 0.05 * sfx_i),
                        duration=sfx_dur,
                        line_index=idx,
                    )
                )

        prev_voice_end = start + voice_dur
        prev_pause = float(sl.pause_sec or 0.0)
        script_lines.append(sl)
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

    scene_music, music_src, music_reason = resolve_music_func(script_lines, scene_audio_dir)
    music_event = AudioEvent(type="music", file=str(scene_music), start=0.0, duration=0.0, line_index=-1) if scene_music else None
    events = build_cinematic_timeline(voice_events, sfx_events, music_event)
    narration_path = scene_audio_dir / f"scene_{int(scene.get('scene_id', 0)):03d}.mp3"
    mix_func(events, narration_path, scene_audio_dir)
    duration = max(0.0, max((e.start + e.duration for e in voice_events), default=0.0))
    return {
        "scene_id": int(scene.get("scene_id", 0)),
        "audio": str(narration_path),
        "timeline": build_timeline(events),
        "segments": segments,
        "duration": duration,
        "music_source": music_src,
        "music_reason": music_reason,
    }

