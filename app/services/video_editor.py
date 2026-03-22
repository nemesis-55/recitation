from __future__ import annotations

import math
from pathlib import Path

from app.config import settings
from app.utils.ffmpeg_runner import probe_duration_seconds, run_ffmpeg


def assemble_video(
    clips: list[Path],
    narration_path: Path,
    output_path: Path,
    subtitles_path: Path | None = None,
    bgm_path: str | None = None,
    playback_speed: float | None = None,
    profile: str = "reel",
) -> Path:
    speed = max(0.25, min(4.0, float(playback_speed if playback_speed is not None else settings.video_playback_speed)))
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

    prepared_video = merged_video
    if abs(speed - 1.0) > 1e-6 or profile.lower() == "youtube":
        speed_video = output_path.parent / f"video_prepared_{profile}.mp4"
        if profile.lower() == "youtube":
            vf = (
                f"scale={settings.youtube_target_width}:{settings.youtube_target_height}:force_original_aspect_ratio=decrease,"
                f"pad={settings.youtube_target_width}:{settings.youtube_target_height}:(ow-iw)/2:(oh-ih)/2,"
                "eq=contrast=1.03:saturation=1.05,unsharp=5:5:0.5:3:3:0.0"
            )
            if abs(speed - 1.0) > 1e-6:
                vf += f",setpts=PTS/{speed}"
        else:
            vf = f"setpts=PTS/{speed}"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(merged_video),
                "-filter:v",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(speed_video),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
        prepared_video = speed_video

    prepared_audio = output_path.parent / "narration_prepared.m4a"
    if abs(speed - 1.0) > 1e-6:
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(narration_path),
                "-filter:a",
                f"atempo={speed},aresample=async=1:first_pts=0",
                "-c:a",
                "aac",
                str(prepared_audio),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
    else:
        run_ffmpeg(
            ["ffmpeg", "-y", "-i", str(narration_path), "-c:a", "aac", str(prepared_audio)],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )

    if bgm_path:
        mixed_audio = output_path.parent / "narration_with_bgm.m4a"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(prepared_audio),
                "-stream_loop",
                "-1",
                "-i",
                bgm_path,
                "-filter_complex",
                f"[1:a]volume={settings.bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map",
                "[aout]",
                "-c:a",
                "aac",
                str(mixed_audio),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
        prepared_audio = mixed_audio

    mux_cmd = ["ffmpeg", "-y", "-i", str(prepared_video), "-i", str(prepared_audio)]
    if subtitles_path and subtitles_path.exists():
        mux_cmd.extend(["-i", str(subtitles_path)])
    mux_cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
    )
    if subtitles_path and subtitles_path.exists():
        mux_cmd.extend(["-map", "2:0", "-c:s", "mov_text"])
    mux_cmd.extend(
        [
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    run_ffmpeg(mux_cmd, stage="video_editor", timeout_sec=settings.stage_timeout_sec)
    return output_path


def trim_audio_segment(source_audio: Path, output_audio: Path, start_sec: float, end_sec: float) -> Path:
    lo = max(0.0, float(start_sec))
    hi = max(lo + 0.05, float(end_sec))
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{lo:.3f}",
            "-to",
            f"{hi:.3f}",
            "-i",
            str(source_audio),
            "-c:a",
            "aac",
            str(output_audio),
        ],
        stage="video_editor",
        timeout_sec=settings.stage_timeout_sec,
    )
    return output_audio


def split_video_chunks(source_video: Path, output_dir: Path, max_duration_sec: float) -> list[Path]:
    chunk_len = max(5.0, float(max_duration_sec))
    total = max(0.0, float(probe_duration_seconds(source_video)))
    if total <= 0.0:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    chunk_count = int(math.ceil(total / chunk_len))
    for idx in range(chunk_count):
        start_sec = idx * chunk_len
        end_sec = min(total, start_sec + chunk_len)
        if end_sec - start_sec < 0.1:
            continue
        out = output_dir / f"reel_chunk_{idx + 1:03d}.mp4"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start_sec:.3f}",
                "-to",
                f"{end_sec:.3f}",
                "-i",
                str(source_video),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
        chunks.append(out)
    return chunks
