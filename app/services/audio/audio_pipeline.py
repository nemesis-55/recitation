from __future__ import annotations

from pathlib import Path

from app.models.schemas import AudioSegment as AudioSegmentSchema
from app.models.schemas import ScriptLine
from app.services.audio.audio_mixer import mix_audio
from app.services.audio.character_engine import get_voice
from app.services.audio.dialogue_analyzer import analyze_dialogue
from app.services.audio.pause_engine import create_silence_clip, pause_seconds
from app.services.audio.sfx_engine import pick_sfx
from app.services.audio.speech_renderer import render_speech
from app.services.audio.timeline_builder import AudioEvent, build_timeline
from app.services.audio.tts_elevenlabs import generate_tts
from app.services.audio.voice_fx import apply_voice_fx
from app.utils.ffmpeg_runner import probe_duration_seconds
from app.config import settings


def _build_tts_groups(lines: list[ScriptLine]) -> list[list[int]]:
    groups: list[list[int]] = []
    for idx, line in enumerate(lines):
        text = (line.rendered_text or "").strip()
        if not text:
            groups.append([idx])
            continue
        if not settings.audio_grouping_enabled:
            groups.append([idx])
            continue
        if not groups:
            groups.append([idx])
            continue
        prev_group = groups[-1]
        prev_line = lines[prev_group[-1]]
        group_chars = sum(len((lines[i].rendered_text or "")) for i in prev_group)
        compatible = (
            (line.voice == prev_line.voice)
            and ((line.emotion or "neutral").lower() == (prev_line.emotion or "neutral").lower())
            and ((line.panel_path or "") == (prev_line.panel_path or ""))
            and group_chars + len(text) <= max(40, settings.audio_group_max_chars)
        )
        if compatible:
            prev_group.append(idx)
        else:
            groups.append([idx])
    return groups


def run_audio_pipeline(script: list[ScriptLine], audio_dir: Path) -> tuple[Path, list[AudioSegmentSchema], list[dict]]:
    analyzed = analyze_dialogue(script)
    events: list[AudioEvent] = []
    segments: list[AudioSegmentSchema] = []
    sfx_root = Path(__file__).resolve().parents[3] / "assets" / "sfx"
    cursor = 0.0

    for idx, line in enumerate(analyzed):
        line.voice = get_voice(line, idx)
        line.rendered_text = render_speech(line.narration or "", line.emotion or "neutral", float(line.emotion_intensity or 0.5))
        line.pause_sec = pause_seconds((line.emotion or "neutral").lower(), float(line.emotion_intensity or 0.5))

    for group in _build_tts_groups(analyzed):
        first = analyzed[group[0]]
        group_text_parts = [(analyzed[i].rendered_text or "").strip() for i in group if (analyzed[i].rendered_text or "").strip()]
        merged_text = " ".join(group_text_parts).strip()
        group_voice_path = audio_dir / f"group_{group[0]:03d}_{group[-1]:03d}.mp3"
        if merged_text:
            generate_tts(
                text=merged_text,
                voice_id=first.voice,
                emotion=(first.emotion or "neutral").lower(),
                intensity=float(first.emotion_intensity or 0.5),
                output_path=group_voice_path,
            )
            if settings.audio_voice_fx_enabled:
                fx_path = audio_dir / f"group_{group[0]:03d}_{group[-1]:03d}_fx.mp3"
                apply_voice_fx(
                    input_path=group_voice_path,
                    output_path=fx_path,
                    gender=(first.gender or "unknown").lower(),
                    emotion=(first.emotion or "neutral").lower(),
                    intensity=float(first.emotion_intensity or 0.5),
                )
                group_voice_path = fx_path
            group_voice_dur = max(0.05, probe_duration_seconds(group_voice_path))
        else:
            group_voice_dur = 0.0

        text_weights = [max(1, len((analyzed[i].rendered_text or "").strip())) for i in group]
        total_weight = float(sum(text_weights))
        voice_cursor = cursor
        for pos, idx in enumerate(group):
            line = analyzed[idx]
            voice_share = group_voice_dur * (text_weights[pos] / total_weight) if total_weight > 0 else 0.0
            if merged_text:
                events.append(AudioEvent(type="voice", file=str(group_voice_path), start=voice_cursor, duration=voice_share, line_index=idx))
            for sfx in pick_sfx(line, sfx_root):
                events.append(AudioEvent(type="sfx", file=str(sfx), start=voice_cursor + 0.04, duration=0.8, line_index=idx))
            voice_cursor += voice_share

            min_hold = max(0.1, float(settings.min_panel_duration_sec))
            target_pause = max(line.pause_sec or 0.3, min_hold - voice_share)
            pause_path = audio_dir / f"pause_{idx:03d}.mp3"
            create_silence_clip(pause_path, target_pause)
            pause_dur = max(0.05, probe_duration_seconds(pause_path))
            events.append(AudioEvent(type="pause", file=str(pause_path), start=voice_cursor, duration=pause_dur, line_index=idx))
            seg_start = voice_cursor - voice_share
            seg_end = voice_cursor + pause_dur
            segments.append(
                AudioSegmentSchema(
                    line_index=idx,
                    audio_path=str(group_voice_path) if merged_text else str(pause_path),
                    start_sec=seg_start,
                    end_sec=seg_end,
                    duration_sec=voice_share + pause_dur,
                    pause_sec=pause_dur,
                    provider="elevenlabs",
                    voice=line.voice,
                    rendered_text=line.rendered_text,
                )
            )
            line.tts_provider = "elevenlabs"
            voice_cursor += pause_dur
        cursor = voice_cursor

    narration_path = audio_dir / "narration.mp3"
    mix_audio(events=events, output_path=narration_path, work_dir=audio_dir)
    return narration_path, segments, build_timeline(events)
