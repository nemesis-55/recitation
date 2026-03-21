from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.audio.timeline_builder import AudioEvent
from app.utils.ffmpeg_runner import run_ffmpeg


def _mix_voice_and_music(base_track: Path, music_path: Path | None, work_dir: Path) -> Path:
    if not music_path or not music_path.exists():
        return base_track
    out = work_dir / "voice_with_music_bed.mp3"
    vol = max(0.0, min(1.0, float(settings.audio_music_volume)))
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(base_track),
            "-stream_loop",
            "-1",
            "-i",
            str(music_path),
            "-filter_complex",
            f"[1:a]volume={vol}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            str(out),
        ],
        stage="audio_mixer",
    )
    return out


def mix_audio(events: list[AudioEvent], output_path: Path, work_dir: Path, music_path: Path | None = None) -> Path:
    voice_and_pause = [e for e in events if e.type in {"voice", "pause"}]
    sfx_events = [e for e in events if e.type == "sfx"]
    concat_list = work_dir / "audio_concat.txt"
    concat_list.write_text("\n".join([f"file '{Path(e.file).resolve().as_posix()}'" for e in voice_and_pause]), encoding="utf-8")
    base_track = work_dir / "voice_base.mp3"
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
            "-c:a",
            "libmp3lame",
            str(base_track),
        ],
        stage="audio_mixer",
    )

    mixed_voice = _mix_voice_and_music(base_track, music_path, work_dir)

    if not sfx_events:
        output_path.write_bytes(mixed_voice.read_bytes())
        return output_path

    inputs = ["-i", str(mixed_voice)]
    filters = []
    mix_inputs = ["[0:a]"]
    next_input_index = 1
    if settings.audio_ambience_path:
        ambience_path = Path(settings.audio_ambience_path)
        if ambience_path.exists():
            inputs.extend(["-stream_loop", "-1", "-i", str(ambience_path)])
            filters.append(f"[{next_input_index}:a]volume={settings.audio_ambience_volume}[amb]")
            mix_inputs.append("[amb]")
            next_input_index += 1
    for idx, evt in enumerate(sfx_events, start=1):
        inputs.extend(["-i", str(evt.file)])
        delay_ms = int(max(0.0, evt.start) * 1000)
        filters.append(f"[{next_input_index}:a]volume={settings.audio_sfx_volume},adelay={delay_ms}|{delay_ms}[s{idx}]")
        mix_inputs.append(f"[s{idx}]")
        next_input_index += 1
    filters.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[aout]")
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
            str(output_path),
        ],
        stage="audio_mixer",
    )
    return output_path
