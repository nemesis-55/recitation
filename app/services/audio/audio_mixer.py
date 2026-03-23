from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.audio.timeline_builder import AudioEvent
from app.utils.ffmpeg_runner import probe_duration_seconds, run_ffmpeg
from app.utils.pipeline_debug import log_pipeline_debug


def _music_stem_processing_chain() -> str:
    """
    FFmpeg filters applied to the **music bed only** (after atrim to scene length, before volume).
    Improves clarity under voice without changing duration or voice/SFX timing.
    """
    parts: list[str] = []
    hp = int(getattr(settings, "audio_mixer_music_highpass_hz", 0) or 0)
    if hp > 0:
        parts.append(f"highpass=f={max(20, min(500, hp))}")
    if bool(getattr(settings, "audio_mixer_music_dynaudnorm_enabled", True)):
        parts.append("dynaudnorm=f=200:g=9")
    if not parts:
        return ""
    # No leading comma: callers append `,{stem},` after atrim or after `[music_bus]` (see layered path).
    return ",".join(parts)


def _mix_target_duration_sec(events: list[AudioEvent]) -> float:
    max_end = 0.0
    for evt in events:
        end = max(0.0, float(evt.start)) + max(0.0, float(evt.duration))
        if end > max_end:
            max_end = end
    # Small tail to avoid cutting decay at exact boundary.
    return max(1.0, max_end + 0.6)


def _amix_refs(filters: list[str], refs: list[str], out_label: str, chunk_prefix: str, duration_mode: str) -> str:
    if not refs:
        raise ValueError("amix refs cannot be empty")
    if len(refs) == 1:
        filters.append(f"{refs[0]}anull[{out_label}]")
        return f"[{out_label}]"
    # Keep simple single-pass amix for small groups (stable and test-friendly).
    if len(refs) <= 16:
        filters.append(f"{''.join(refs)}amix=inputs={len(refs)}:duration={duration_mode}:normalize=0[{out_label}]")
        return f"[{out_label}]"
    # ffmpeg filtergraphs with very large amix fan-in can produce unstable/truncated output.
    # Mix in deterministic chunks, then mix stems.
    chunk_size = 16
    stems: list[str] = []
    for idx in range(0, len(refs), chunk_size):
        chunk = refs[idx : idx + chunk_size]
        stem = f"{chunk_prefix}{idx // chunk_size}"
        filters.append(f"{''.join(chunk)}amix=inputs={len(chunk)}:duration=longest:normalize=0[{stem}]")
        stems.append(f"[{stem}]")
    if len(stems) == 1:
        filters.append(f"{stems[0]}anull[{out_label}]")
    else:
        filters.append(f"{''.join(stems)}amix=inputs={len(stems)}:duration={duration_mode}:normalize=0[{out_label}]")
    return f"[{out_label}]"


def _mix_audio_sequential_voice_music(
    voice_events: list[AudioEvent],
    sfx_events: list[AudioEvent],
    music_events: list[AudioEvent],
    output_path: Path,
    target_duration_sec: float,
) -> None:
    sorted_voice = sorted(voice_events, key=lambda e: (float(e.start), int(e.line_index)))
    cmd: list[str] = ["ffmpeg", "-y"]
    filters: list[str] = []
    concat_refs: list[str] = []
    input_idx = 0
    cursor_sec = 0.0

    for i, evt in enumerate(sorted_voice):
        start_sec = max(0.0, float(evt.start))
        dur_sec = max(0.05, float(evt.duration))
        gap_sec = max(0.0, start_sec - cursor_sec)
        if gap_sec > 0.001:
            cmd.extend(["-f", "lavfi", "-t", f"{gap_sec:.3f}", "-i", "anullsrc=r=44100:cl=mono"])
            g_ref = f"[g{i}]"
            filters.append(f"[{input_idx}:a]anull{g_ref}")
            concat_refs.append(g_ref)
            input_idx += 1

        cmd.extend(["-i", str(evt.file)])
        v_ref = f"[v{i}]"
        filters.append(
            f"[{input_idx}:a]atrim=0:{dur_sec:.3f},asetpts=N/SR/TB,volume={settings.audio_mixer_voice_gain}{v_ref}"
        )
        concat_refs.append(v_ref)
        input_idx += 1
        cursor_sec = max(cursor_sec, start_sec + dur_sec)

    tail_sec = max(0.0, target_duration_sec - cursor_sec)
    if tail_sec > 0.001:
        cmd.extend(["-f", "lavfi", "-t", f"{tail_sec:.3f}", "-i", "anullsrc=r=44100:cl=mono"])
        tail_ref = "[gtail]"
        filters.append(f"[{input_idx}:a]anull{tail_ref}")
        concat_refs.append(tail_ref)
        input_idx += 1

    filters.append(f"{''.join(concat_refs)}concat=n={len(concat_refs)}:v=0:a=1[voice_out]")
    # region agent log
    log_pipeline_debug(
        run_id="pre-fix-1",
        hypothesis_id="H2",
        location="audio_mixer.py:_mix_audio_sequential_voice_music",
        message="Sequential builder stats",
        data={
            "voice_events": len(sorted_voice),
            "sfx_events": len(sfx_events),
            "music_events": len(music_events),
            "cursor_sec": round(cursor_sec, 3),
            "tail_sec": round(tail_sec, 3),
            "target_duration_sec": round(target_duration_sec, 3),
            "concat_refs": len(concat_refs),
        },
    )
    # endregion

    sfx_refs: list[str] = []
    for i, evt in enumerate(sfx_events):
        cmd.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, float(evt.start)) * 1000)
        max_dur = max(0.05, float(evt.duration))
        sfx_ref = f"[sx{i}]"
        filters.append(f"[{input_idx}:a]atrim=0:{max_dur:.3f},adelay={delay_ms}|{delay_ms}{sfx_ref}")
        sfx_refs.append(sfx_ref)
        input_idx += 1
    if sfx_refs:
        _amix_refs(filters, sfx_refs, "sfx_bus", "sqx_", "longest")
    else:
        filters.append(f"anullsrc=r=44100:cl=mono,atrim=0:{target_duration_sec:.3f}[sfx_bus]")
    sfx_gain = max(0.2, min(1.0, float(settings.audio_mixer_sfx_gain or 0.6)))
    filters.append(f"[sfx_bus]volume={sfx_gain:.3f}[sfx_out]")

    has_music = len(music_events) > 0
    if has_music:
        cmd.extend(["-stream_loop", "-1", "-i", str(music_events[0].file)])
        music_idx = input_idx
        music_gain = max(0.05, min(0.3, float(settings.audio_mixer_music_gain or 0.18)))
        stem = _music_stem_processing_chain()
        if stem:
            filters.append(
                f"[{music_idx}:a]atrim=0:{target_duration_sec:.3f},{stem},volume={music_gain:.3f}[music_out]"
            )
        else:
            filters.append(f"[{music_idx}:a]atrim=0:{target_duration_sec:.3f},volume={music_gain:.3f}[music_out]")
        if settings.audio_mixer_ducking_enabled:
            filters.append(
                "[music_out][voice_out]sidechaincompress="
                f"threshold={settings.audio_mixer_ducking_threshold}:"
                f"ratio={settings.audio_mixer_ducking_ratio}:"
                f"attack={settings.audio_mixer_ducking_attack_ms}:"
                f"release={settings.audio_mixer_ducking_release_ms}"
                "[music_ducked]"
            )
            filters.append("[voice_out][music_ducked][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")
        else:
            filters.append("[voice_out][music_out][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")
    else:
        filters.append("[voice_out][sfx_out]amix=inputs=2:duration=first:normalize=0[preout]")

    hp = max(20, int(settings.audio_mixer_highpass_hz))
    lp = max(hp + 1000, int(settings.audio_mixer_lowpass_hz))
    filters.append(f"[preout]highpass=f={hp},lowpass=f={lp}[shaped]")
    if settings.audio_mixer_normalize_loudness:
        filters.append("[shaped]loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95[aout]")
    else:
        filters.append("[shaped]alimiter=limit=0.95[aout]")

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-t",
            f"{target_duration_sec:.3f}",
            str(output_path),
        ]
    )
    run_ffmpeg(cmd, stage="audio_mixer")
    # region agent log
    log_pipeline_debug(
        run_id="pre-fix-1",
        hypothesis_id="H2",
        location="audio_mixer.py:_mix_audio_sequential_voice_music",
        message="Sequential ffmpeg finished",
        data={"cmd_args": len(cmd), "output_path": str(output_path)},
    )
    # endregion


def _build_voice_timeline_rescue(
    voice_events: list[AudioEvent],
    work_dir: Path,
    target_duration_sec: float,
) -> Path:
    sorted_voice = sorted(voice_events, key=lambda e: (float(e.start), int(e.line_index)))
    segments_dir = work_dir / "rescue_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    concat_list = segments_dir / "voice_concat.txt"
    refs: list[Path] = []
    cursor_sec = 0.0
    voice_gain = float(settings.audio_mixer_voice_gain)

    for i, evt in enumerate(sorted_voice):
        start_sec = max(0.0, float(evt.start))
        dur_sec = max(0.05, float(evt.duration))
        gap_sec = max(0.0, start_sec - cursor_sec)
        if gap_sec > 0.001:
            gap_path = segments_dir / f"gap_{i:04d}.wav"
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-t",
                    f"{gap_sec:.3f}",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(gap_path),
                ],
                stage="audio_mixer",
            )
            refs.append(gap_path)

        voice_path = segments_dir / f"voice_{i:04d}.wav"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(evt.file),
                "-t",
                f"{dur_sec:.3f}",
                "-af",
                f"volume={voice_gain:.3f}",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(voice_path),
            ],
            stage="audio_mixer",
        )
        refs.append(voice_path)
        cursor_sec = max(cursor_sec, start_sec + dur_sec)

    tail_sec = max(0.0, target_duration_sec - cursor_sec)
    if tail_sec > 0.001:
        tail_path = segments_dir / "tail.wav"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-t",
                f"{tail_sec:.3f}",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(tail_path),
            ],
            stage="audio_mixer",
        )
        refs.append(tail_path)

    concat_lines = []
    for p in refs:
        escaped = str(p).replace("'", "'\\''")
        concat_lines.append(f"file '{escaped}'")
    concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    voice_timeline = work_dir / "voice_timeline_rescue.wav"
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(voice_timeline),
        ],
        stage="audio_mixer",
    )
    return voice_timeline


def _mix_audio_rescue(
    voice_events: list[AudioEvent],
    sfx_events: list[AudioEvent],
    music_events: list[AudioEvent],
    output_path: Path,
    target_duration_sec: float,
    work_dir: Path,
) -> None:
    voice_timeline = _build_voice_timeline_rescue(voice_events, work_dir, target_duration_sec)
    cmd: list[str] = ["ffmpeg", "-y", "-i", str(voice_timeline)]
    filters: list[str] = []
    input_idx = 1
    sfx_refs: list[str] = []

    for i, evt in enumerate(sfx_events):
        cmd.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, float(evt.start)) * 1000)
        max_dur = max(0.05, float(evt.duration))
        ref = f"[sx{i}]"
        filters.append(f"[{input_idx}:a]atrim=0:{max_dur:.3f},adelay={delay_ms}|{delay_ms}{ref}")
        sfx_refs.append(ref)
        input_idx += 1
    if sfx_refs:
        _amix_refs(filters, sfx_refs, "sfx_bus", "rsx_", "longest")
    else:
        filters.append(f"anullsrc=r=44100:cl=mono,atrim=0:{target_duration_sec:.3f}[sfx_bus]")
    sfx_gain = max(0.2, min(1.0, float(settings.audio_mixer_sfx_gain or 0.6)))
    filters.append(f"[sfx_bus]volume={sfx_gain:.3f}[sfx_out]")

    if music_events:
        cmd.extend(["-stream_loop", "-1", "-i", str(music_events[0].file)])
        music_idx = input_idx
        music_gain = max(0.05, min(0.3, float(settings.audio_mixer_music_gain or 0.18)))
        stem = _music_stem_processing_chain()
        if stem:
            filters.append(
                f"[{music_idx}:a]atrim=0:{target_duration_sec:.3f},{stem},volume={music_gain:.3f}[music_out]"
            )
        else:
            filters.append(f"[{music_idx}:a]atrim=0:{target_duration_sec:.3f},volume={music_gain:.3f}[music_out]")
        if settings.audio_mixer_ducking_enabled:
            filters.append(
                "[music_out][0:a]sidechaincompress="
                f"threshold={settings.audio_mixer_ducking_threshold}:"
                f"ratio={settings.audio_mixer_ducking_ratio}:"
                f"attack={settings.audio_mixer_ducking_attack_ms}:"
                f"release={settings.audio_mixer_ducking_release_ms}"
                "[music_ducked]"
            )
            filters.append("[0:a][music_ducked][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")
        else:
            filters.append("[0:a][music_out][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")
    else:
        filters.append("[0:a][sfx_out]amix=inputs=2:duration=first:normalize=0[preout]")

    hp = max(20, int(settings.audio_mixer_highpass_hz))
    lp = max(hp + 1000, int(settings.audio_mixer_lowpass_hz))
    filters.append(f"[preout]highpass=f={hp},lowpass=f={lp}[shaped]")
    if settings.audio_mixer_normalize_loudness:
        filters.append("[shaped]loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95[aout]")
    else:
        filters.append("[shaped]alimiter=limit=0.95[aout]")

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-t",
            f"{target_duration_sec:.3f}",
            str(output_path),
        ]
    )
    run_ffmpeg(cmd, stage="audio_mixer")


def mix_audio(events: list[AudioEvent], output_path: Path, work_dir: Path, music_path: Path | None = None) -> Path:
    all_events = list(events)
    if music_path is not None:
        all_events.append(AudioEvent(type="music", file=str(music_path), start=0.0, duration=0.0, line_index=-1))

    voice_events = [e for e in all_events if e.type in {"voice", "pause"}]
    sfx_events = [e for e in all_events if e.type == "sfx"]
    music_events = [e for e in all_events if e.type == "music"]
    if not voice_events:
        raise ValueError("audio_mixer requires at least one voice/pause event")
    target_duration_sec = _mix_target_duration_sec(voice_events + sfx_events)
    # region agent log
    log_pipeline_debug(
        run_id="pre-fix-1",
        hypothesis_id="H1",
        location="audio_mixer.py:mix_audio",
        message="Mix entry counts",
        data={
            "voice_events": len(voice_events),
            "sfx_events": len(sfx_events),
            "music_events": len(music_events),
            "target_duration_sec": round(target_duration_sec, 3),
            "first_voice_start": round(float(min((e.start for e in voice_events), default=0.0)), 3),
            "last_voice_end": round(
                float(max(((e.start + e.duration) for e in voice_events), default=0.0)),
                3,
            ),
        },
    )
    # endregion

    # Long panel-wise episodes can exceed stable fan-in limits for layered amix graphs.
    # Build a deterministic sequential voice track for those runs.
    if len(voice_events) >= 24:
        # region agent log
        log_pipeline_debug(
            run_id="pre-fix-1",
            hypothesis_id="H1",
            location="audio_mixer.py:mix_audio",
            message="Branch selected sequential",
            data={"voice_events": len(voice_events), "sfx_events": len(sfx_events)},
        )
        # endregion
        _mix_audio_sequential_voice_music(voice_events, sfx_events, music_events, output_path, target_duration_sec)
        if output_path.exists():
            try:
                actual_sec = float(probe_duration_seconds(output_path))
                if actual_sec < max(1.0, target_duration_sec * 0.80):
                    raise RuntimeError(
                        f"audio_mixer_truncated actual={actual_sec:.3f}s target={target_duration_sec:.3f}s"
                    )
                # region agent log
                log_pipeline_debug(
                    run_id="pre-fix-1",
                    hypothesis_id="H2",
                    location="audio_mixer.py:mix_audio",
                    message="Sequential probe duration",
                    data={"actual_sec": round(actual_sec, 3), "target_sec": round(target_duration_sec, 3)},
                )
                # endregion
            except Exception as exc:
                # region agent log
                log_pipeline_debug(
                    run_id="pre-fix-1",
                    hypothesis_id="H2",
                    location="audio_mixer.py:mix_audio",
                    message="Sequential probe failed",
                    data={"error": str(exc), "output_path": str(output_path)},
                )
                # endregion
                # region agent log
                log_pipeline_debug(
                    run_id="pre-fix-1",
                    hypothesis_id="H5",
                    location="audio_mixer.py:mix_audio",
                    message="Activating rescue mixer",
                    data={"target_sec": round(target_duration_sec, 3), "error": str(exc)},
                )
                # endregion
                _mix_audio_rescue(voice_events, sfx_events, music_events, output_path, target_duration_sec, work_dir)
                repaired_sec = float(probe_duration_seconds(output_path))
                # region agent log
                log_pipeline_debug(
                    run_id="pre-fix-1",
                    hypothesis_id="H5",
                    location="audio_mixer.py:mix_audio",
                    message="Rescue probe duration",
                    data={"actual_sec": round(repaired_sec, 3), "target_sec": round(target_duration_sec, 3)},
                )
                # endregion
                if repaired_sec < max(1.0, target_duration_sec * 0.80):
                    raise RuntimeError(
                        f"Audio mix validation failed for {output_path}: "
                        f"audio_mixer_truncated actual={repaired_sec:.3f}s target={target_duration_sec:.3f}s"
                    ) from exc
        return output_path

    inputs: list[str] = []
    filters: list[str] = []
    voice_refs: list[str] = []
    sfx_refs: list[str] = []
    music_refs: list[str] = []

    input_idx = 0
    for i, evt in enumerate(voice_events):
        inputs.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, evt.start) * 1000)
        max_dur = max(0.05, float(evt.duration))
        ref = f"[v{i}]"
        filters.append(
            f"[{input_idx}:a]atrim=0:{max_dur:.3f},volume={settings.audio_mixer_voice_gain},adelay={delay_ms}|{delay_ms}{ref}"
        )
        voice_refs.append(ref)
        input_idx += 1

    for i, evt in enumerate(sfx_events):
        inputs.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, evt.start) * 1000)
        max_dur = max(0.05, float(evt.duration))
        ref = f"[s{i}]"
        filters.append(f"[{input_idx}:a]atrim=0:{max_dur:.3f},adelay={delay_ms}|{delay_ms}{ref}")
        sfx_refs.append(ref)
        input_idx += 1

    for i, evt in enumerate(music_events):
        if i == 0:
            inputs.extend(["-stream_loop", "-1", "-i", str(evt.file)])
        else:
            inputs.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, evt.start) * 1000)
        ref = f"[m{i}]"
        filters.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}{ref}")
        music_refs.append(ref)
        input_idx += 1

    # Anchor guarantees output bus spans target duration even with sparse delayed clips.
    filters.append(f"anullsrc=r=44100:cl=mono,atrim=0:{target_duration_sec:.3f}[voice_anchor]")
    if len(voice_refs) == 1:
        filters.append("[voice_anchor]" + voice_refs[0] + "amix=inputs=2:duration=first:normalize=0[voice_bus]")
    elif 1 < len(voice_refs) <= 16:
        filters.append(
            "[voice_anchor]"
            + "".join(voice_refs)
            + f"amix=inputs={len(voice_refs) + 1}:duration=first:normalize=0[voice_bus]"
        )
    elif len(voice_refs) > 16:
        mixed_voice = _amix_refs(filters, voice_refs, "voice_mix", "vstem_", "longest")
        filters.append(f"[voice_anchor]{mixed_voice}amix=inputs=2:duration=first:normalize=0[voice_bus]")
    else:
        filters.append("[voice_anchor]anull[voice_bus]")
    filters.append("[voice_bus]acompressor=threshold=-18dB:ratio=2:attack=5:release=50[comp]")
    if settings.audio_mixer_use_loudnorm:
        filters.append("[comp]loudnorm=I=-16:TP=-1.5:LRA=11[voice_out]")
    else:
        filters.append("[comp]dynaudnorm=f=250:g=15[voice_out]")

    if len(sfx_refs) > 0:
        _amix_refs(filters, sfx_refs, "sfx_bus", "sstem_", "longest")
    else:
        filters.append(f"anullsrc=r=44100:cl=mono,atrim=0:{target_duration_sec:.3f}[sfx_bus]")
    sfx_gain = max(0.2, min(1.0, float(settings.audio_mixer_sfx_gain or 0.6)))
    filters.append(f"[sfx_bus]volume={sfx_gain:.3f}[sfx_out]")

    if len(music_refs) > 0:
        _amix_refs(filters, music_refs, "music_bus", "mstem_", "longest")
    else:
        filters.append(f"anullsrc=r=44100:cl=mono,atrim=0:{target_duration_sec:.3f}[music_bus]")
    music_gain = max(0.05, min(0.3, float(settings.audio_mixer_music_gain or 0.18)))
    stem = _music_stem_processing_chain()
    if stem:
        filters.append(f"[music_bus]{stem},volume={music_gain:.3f}[music_out]")
    else:
        filters.append(f"[music_bus]volume={music_gain:.3f}[music_out]")

    if settings.audio_mixer_ducking_enabled:
        filters.append(
            "[music_out][voice_out]sidechaincompress="
            f"threshold={settings.audio_mixer_ducking_threshold}:"
            f"ratio={settings.audio_mixer_ducking_ratio}:"
            f"attack={settings.audio_mixer_ducking_attack_ms}:"
            f"release={settings.audio_mixer_ducking_release_ms}"
            "[music_ducked]"
        )
        filters.append("[voice_out][music_ducked][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")
    else:
        filters.append("[voice_out][music_out][sfx_out]amix=inputs=3:duration=first:normalize=0[preout]")

    hp = max(20, int(settings.audio_mixer_highpass_hz))
    lp = max(hp + 1000, int(settings.audio_mixer_lowpass_hz))
    filters.append(f"[preout]atrim=0:{target_duration_sec:.3f},asetpts=N/SR/TB,highpass=f={hp},lowpass=f={lp}[shaped]")
    if settings.audio_mixer_normalize_loudness:
        filters.append("[shaped]loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95[aout]")
    else:
        filters.append("[shaped]alimiter=limit=0.95[aout]")

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-t",
            f"{target_duration_sec:.3f}",
            str(output_path),
        ],
        stage="audio_mixer",
    )
    # region agent log
    log_pipeline_debug(
        run_id="pre-fix-1",
        hypothesis_id="H1",
        location="audio_mixer.py:mix_audio",
        message="Branch selected layered",
        data={"voice_events": len(voice_events), "sfx_events": len(sfx_events), "filter_count": len(filters)},
    )
    # endregion
    # Guardrail: never accept severely truncated mixes silently.
    if output_path.exists():
        try:
            actual_sec = float(probe_duration_seconds(output_path))
            if actual_sec < max(1.0, target_duration_sec * 0.80):
                raise RuntimeError(
                    f"audio_mixer_truncated actual={actual_sec:.3f}s target={target_duration_sec:.3f}s"
                )
            # region agent log
            log_pipeline_debug(
                run_id="pre-fix-1",
                hypothesis_id="H3",
                location="audio_mixer.py:mix_audio",
                message="Layered probe duration",
                data={"actual_sec": round(actual_sec, 3), "target_sec": round(target_duration_sec, 3)},
            )
            # endregion
        except Exception as exc:
            # region agent log
            log_pipeline_debug(
                run_id="pre-fix-1",
                hypothesis_id="H3",
                location="audio_mixer.py:mix_audio",
                message="Layered probe failed",
                data={"error": str(exc), "output_path": str(output_path)},
            )
            # endregion
            # region agent log
            log_pipeline_debug(
                run_id="pre-fix-1",
                hypothesis_id="H5",
                location="audio_mixer.py:mix_audio",
                message="Activating rescue mixer from layered path",
                data={"target_sec": round(target_duration_sec, 3), "error": str(exc)},
            )
            # endregion
            _mix_audio_rescue(voice_events, sfx_events, music_events, output_path, target_duration_sec, work_dir)
            repaired_sec = float(probe_duration_seconds(output_path))
            # region agent log
            log_pipeline_debug(
                run_id="pre-fix-1",
                hypothesis_id="H5",
                location="audio_mixer.py:mix_audio",
                message="Rescue probe duration from layered path",
                data={"actual_sec": round(repaired_sec, 3), "target_sec": round(target_duration_sec, 3)},
            )
            # endregion
            if repaired_sec < max(1.0, target_duration_sec * 0.80):
                raise RuntimeError(
                    f"Audio mix validation failed for {output_path}: "
                    f"audio_mixer_truncated actual={repaired_sec:.3f}s target={target_duration_sec:.3f}s"
                ) from exc
    return output_path
