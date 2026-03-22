from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine, SrtTimelineLine
from app.services.audio.audio_mixer import mix_audio
from app.services.audio.audio_rule_engine import resolve_audio_plan
from app.services.audio.character_engine import get_character_profile, get_voice
from app.services.audio.emotion_engine import analyze_emotion
from app.services.audio.elevenlabs_engine import generate_sfx_event
from app.services.audio.pause_engine import create_silence_clip
from app.services.audio.pause_engine import pause_seconds
from app.services.audio.sfx_alignment_engine import align_sfx
from app.services.audio.speech_renderer import render_speech
from app.services.audio.timeline_builder import AudioEvent, build_cinematic_timeline, build_timeline
from app.services.audio.tts_elevenlabs import generate_tts
from app.services.audio.music_engine import resolve_music_bed
from app.utils.ffmpeg_runner import probe_duration_seconds
from app.services.audio.episode_state import EpisodeState


_SFX_PROMPTS: dict[str, str] = {
    "impact": "Cinematic impact hit, tight transient and deep thump",
    "thump": "Body thump impact, low-frequency floor hit",
    "movement": "Fast cloth movement whoosh, short pass-by",
    "cough": "Short dry cough vocal effect, natural and clean, no words",
}


def _merge_sfx_plan(rule_sfx: list[str], explicit_sfx: list[str]) -> list[str]:
    allowed = {"impact", "thump", "movement", "cough"}
    out: list[str] = []
    for evt in explicit_sfx + rule_sfx:
        e = str(evt).strip().lower()
        if e in allowed and e in _SFX_PROMPTS and e not in out:
            out.append(e)
    return out


def _dominant_music_type(values: list[str]) -> str | None:
    clean = [str(v).strip().lower() for v in values if str(v).strip()]
    if not clean:
        return None
    counts: dict[str, int] = {}
    for val in clean:
        counts[val] = counts.get(val, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _to_script_line(item: SrtTimelineLine, panel_path: str) -> ScriptLine:
    return ScriptLine(
        panel_path=panel_path,
        narration=item.text,
        speaker=item.speaker,
        emotion=item.emotion,
        emotion_intensity=item.intensity,
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _scene_curve_value(index: int, total: int) -> float:
    if total <= 1:
        return 0.5
    pos = float(index) / float(max(1, total - 1))
    if pos <= 0.5:
        return round(0.2 + (0.6 * pos), 3)  # 0.2 -> 0.5
    return round(0.5 + (0.8 * (pos - 0.5)), 3)  # 0.5 -> 0.9


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
    music_type_votes: list[str] = []

    max_refine_lines = max(0, int(settings.openai_emotion_refine_max_lines))
    for idx, line in enumerate(scene_lines):
        panel_path = scene_panel_paths[min(idx, max(0, len(scene_panel_paths) - 1))]
        sl = _to_script_line(line, panel_path=panel_path)
        speaker_key = (sl.speaker or "unknown_1").strip().lower()
        sl.voice = episode_state.voice_map.get(speaker_key) or get_voice(sl, int(line.index))
        base_emotion = str(sl.emotion or "neutral").lower()
        base_intensity = float(sl.emotion_intensity or 0.5)
        scene_emotion = str(scene.get("scene_emotion", "neutral")).lower()
        if idx < max_refine_lines and (sl.narration or "").strip():
            refined_emotion, refined_intensity = analyze_emotion(
                sl.narration,
                scene_emotion,
                base_emotion,
                base_intensity,
            )
        else:
            refined_emotion, refined_intensity = base_emotion, base_intensity
        curve = _scene_curve_value(idx, len(scene_lines))
        effective_intensity = _clamp01((float(refined_intensity) * 0.65) + (curve * 0.35))
        sl.emotion = refined_emotion
        sl.emotion_intensity = effective_intensity
        profile = get_character_profile(sl, int(line.index))
        plan = resolve_audio_plan(
            sl.narration,
            sl.emotion,
            effective_intensity,
            str(scene.get("scene_type") or scene.get("description", "neutral")),
        )
        profile = {**profile, **plan.get("voice_settings", {})}
        if str(plan.get("music_type", "")).strip():
            music_type_votes.append(str(plan.get("music_type")))
        sl.pause_sec = float(plan.get("pause", pause_seconds(sl.emotion, effective_intensity)))
        sl.rendered_text = render_speech(
            sl.narration,
            sl.emotion,
            effective_intensity,
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
                intensity=effective_intensity,
                output_path=voice_path,
                profile=profile,
            )
            voice_dur = max(0.05, probe_func(voice_path))
        else:
            create_silence_clip(voice_path, slot_dur)
            voice_dur = slot_dur
        voice_events.append(AudioEvent(type="voice", file=str(voice_path), start=start, duration=voice_dur, line_index=idx))

        explicit_sfx = [str(x).strip().lower() for x in (line.sfx_cues or []) if str(x).strip()]
        merged_sfx = _merge_sfx_plan(list(plan.get("sfx_plan", [])), explicit_sfx)
        if settings.elevenlabs_sfx_enabled and merged_sfx:
            sfx_limit = max(1 if curve < 0.55 else 2, len(explicit_sfx))
            for sfx_i, evt in enumerate(merged_sfx[:sfx_limit], start=1):
                prompt = _SFX_PROMPTS.get(str(evt), "")
                if not prompt:
                    continue
                sfx_path = scene_audio_dir / f"sfx_{idx:03d}_{sfx_i}.mp3"
                generate_sfx_event(prompt, 0.75, sfx_path)
                sfx_dur = max(0.05, probe_func(sfx_path))
                aligned = align_sfx(sl.rendered_text or sl.narration, voice_dur, str(evt))
                sfx_events.append(
                    AudioEvent(
                        type="sfx",
                        file=str(sfx_path),
                        start=max(0.0, start + float(aligned.get("timestamp", 0.0))),
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
                pause_sec=0.0,
                provider="elevenlabs",
                voice=sl.voice,
                rendered_text=sl.rendered_text,
            )
        )

    # Persist actual inter-line silence into segment metadata for timeline parity.
    for i in range(max(0, len(segments) - 1)):
        gap = max(0.0, float(segments[i + 1].start_sec) - float(segments[i].end_sec))
        segments[i].pause_sec = gap

    scene_music_type = _dominant_music_type(music_type_votes)
    try:
        scene_music, music_src, music_reason = resolve_music_func(script_lines, scene_audio_dir, scene_music_type)
    except TypeError:
        # Backward compatible test patch points with 2-arg resolve_music_bed.
        scene_music, music_src, music_reason = resolve_music_func(script_lines, scene_audio_dir)
    music_event = AudioEvent(type="music", file=str(scene_music), start=0.0, duration=0.0, line_index=-1) if scene_music else None
    events = build_cinematic_timeline(voice_events, sfx_events, music_event)
    narration_path = scene_audio_dir / f"scene_{int(scene.get('scene_id', 0)):03d}.mp3"
    mix_func(events, narration_path, scene_audio_dir)
    voice_tail = max((float(s.end_sec) + float(s.pause_sec) for s in segments), default=0.0)
    sfx_tail = max((float(e.start) + float(e.duration) for e in sfx_events), default=0.0)
    duration = max(0.0, voice_tail, sfx_tail)
    return {
        "scene_id": int(scene.get("scene_id", 0)),
        "audio": str(narration_path),
        "timeline": build_timeline(events),
        "segments": segments,
        "duration": duration,
        "music_source": music_src,
        "music_reason": music_reason,
    }

