from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.audio.timeline_builder import AudioEvent
from app.utils.ffmpeg_runner import run_ffmpeg


def _mix_target_duration_sec(events: list[AudioEvent]) -> float:
    max_end = 0.0
    for evt in events:
        end = max(0.0, float(evt.start)) + max(0.0, float(evt.duration))
        if end > max_end:
            max_end = end
    # Small tail to avoid cutting decay at exact boundary.
    return max(1.0, max_end + 0.6)


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
        filters.append(
            f"[{input_idx}:a]atrim=0:{max_dur:.3f},volume={settings.audio_mixer_sfx_gain},adelay={delay_ms}|{delay_ms}{ref}"
        )
        sfx_refs.append(ref)
        input_idx += 1

    for i, evt in enumerate(music_events):
        if i == 0:
            inputs.extend(["-stream_loop", "-1", "-i", str(evt.file)])
        else:
            inputs.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, evt.start) * 1000)
        ref = f"[m{i}]"
        filters.append(f"[{input_idx}:a]volume={settings.audio_mixer_music_gain},adelay={delay_ms}|{delay_ms}{ref}")
        music_refs.append(ref)
        input_idx += 1

    fg_refs = voice_refs + sfx_refs
    if len(fg_refs) == 1:
        filters.append(f"{fg_refs[0]}anull[fg]")
    else:
        filters.append(f"{''.join(fg_refs)}amix=inputs={len(fg_refs)}:duration=longest:normalize=0[fg]")

    if music_refs:
        if len(music_refs) == 1:
            filters.append(f"{music_refs[0]}anull[music]")
        else:
            filters.append(
                f"{''.join(music_refs)}amix=inputs={len(music_refs)}:duration=longest:normalize=0[music]"
            )
        if settings.audio_mixer_ducking_enabled:
            filters.append("[fg]asplit=2[fg_main][fg_side]")
            filters.append(
                "[music][fg_side]sidechaincompress="
                f"threshold={settings.audio_mixer_ducking_threshold}:"
                f"ratio={settings.audio_mixer_ducking_ratio}:"
                f"attack={settings.audio_mixer_ducking_attack_ms}:"
                f"release={settings.audio_mixer_ducking_release_ms}"
                "[ducked]"
            )
            filters.append("[fg_main][ducked]amix=inputs=2:duration=first:normalize=0[preout]")
        else:
            filters.append("[fg][music]amix=inputs=2:duration=first:normalize=0[preout]")
    else:
        filters.append("[fg]anull[preout]")

    filters.append(f"[preout]atrim=0:{target_duration_sec:.3f},asetpts=N/SR/TB[trimmed]")
    if settings.audio_mixer_normalize_loudness:
        filters.append("[trimmed]dynaudnorm=f=250:g=15,alimiter=limit=0.95[aout]")
    else:
        filters.append("[trimmed]alimiter=limit=0.95[aout]")

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
    return output_path
