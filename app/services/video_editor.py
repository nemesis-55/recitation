from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.utils.errors import PipelineError
from app.utils.ffmpeg_runner import run_ffmpeg


def _escape_subtitles_path(path: Path) -> str:
    # FFmpeg subtitles filter has its own parser; absolute paths should be quoted and escaped.
    value = path.as_posix()
    value = value.replace("\\", "\\\\")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return f"subtitles=filename='{value}'"


def assemble_video(
    clips: list[Path],
    narration_path: Path,
    output_path: Path,
    subtitles_path: Path | None = None,
    bgm_path: str | None = None,
) -> Path:
    playback_speed = 1.25
    list_file = output_path.parent / "concat.txt"
    list_file.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips]), encoding="utf-8")

    merged_video = output_path.parent / "merged.mp4"
    concat_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-an",
        "-r",
        str(settings.default_fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(merged_video),
    ]
    run_ffmpeg(concat_cmd, stage="video_editor", timeout_sec=settings.stage_timeout_sec)

    def _build_final_cmd(try_burn_subtitles: bool) -> list[str]:
        local_inputs = ["-i", str(merged_video)]
        local_maps = ["-map", "[vout]"]
        subtitle_track_index: int | None = None
        audio_from_filter = False
        input_count = 1

        # Pad tail to avoid accumulated frame-quantization drift causing audio overrun.
        video_filter = f"[0:v]tpad=stop_mode=clone:stop_duration=8,setpts=PTS/{playback_speed}[vbase]"
        if try_burn_subtitles and subtitles_path and subtitles_path.exists():
            subtitles_filter = _escape_subtitles_path(subtitles_path)
            video_filter = f"{video_filter};[vbase]{subtitles_filter}[vout]"
        else:
            video_filter = f"{video_filter};[vbase]null[vout]"
            if subtitles_path and subtitles_path.exists():
                subtitle_track_index = input_count
                local_inputs.extend(["-i", str(subtitles_path)])
                local_maps.extend(["-map", f"{subtitle_track_index}:0"])
                input_count += 1

        narration_index = input_count
        local_inputs.extend(["-i", str(narration_path)])
        input_count += 1
        if bgm_path:
            bgm_index = input_count
            local_inputs.extend(["-i", bgm_path])
            input_count += 1
            filter_complex = (
                f"{video_filter};"
                f"[{narration_index}:a]volume=1.0[narr];"
                f"[{bgm_index}:a]volume={settings.bgm_volume}[bgm];"
                "[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[mix];"
                f"[mix]atempo={playback_speed}[aout]"
            )
        else:
            filter_complex = f"{video_filter};[{narration_index}:a]atempo={playback_speed}[aout]"
        local_maps.extend(["-map", "[aout]"])
        audio_from_filter = True

        cmd = [
            "ffmpeg",
            "-y",
            *local_inputs,
            "-filter_complex",
            filter_complex,
            *local_maps,
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
        if audio_from_filter:
            cmd.extend(["-c:a", "aac"])
        if subtitle_track_index is not None:
            cmd.extend(["-c:s", "mov_text"])
        cmd.append(str(output_path))
        return cmd

    try:
        run_ffmpeg(_build_final_cmd(try_burn_subtitles=True), stage="video_editor", timeout_sec=settings.stage_timeout_sec)
    except PipelineError as exc:
        if "No such filter: 'subtitles'" not in exc.message:
            raise
        run_ffmpeg(_build_final_cmd(try_burn_subtitles=False), stage="video_editor", timeout_sec=settings.stage_timeout_sec)
    return output_path
