from __future__ import annotations

import math
from pathlib import Path

from app.config import settings
from app.services.subtitle_generator import scale_srt_for_playback_speed
from app.utils.ffmpeg_runner import probe_duration_seconds, run_ffmpeg


def _aac_bitrate() -> str:
    return f"{max(96, min(320, int(settings.video_mux_audio_bitrate_k)))}k"


def _atempo_filter(speed: float) -> str:
    # atempo supports 0.5..2.0 per stage; chain stages for wider speeds.
    target = max(0.25, min(4.0, float(speed)))
    factors: list[float] = []
    while target > 2.0:
        factors.append(2.0)
        target /= 2.0
    while target < 0.5:
        factors.append(0.5)
        target /= 0.5
    factors.append(target)
    return ",".join([f"atempo={f:.6f}" for f in factors])


def _fit_audio_to_video_duration(audio_path: Path, video_path: Path, output_path: Path) -> Path:
    target_sec = max(0.05, float(probe_duration_seconds(video_path)))
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-filter:a",
            f"apad=pad_dur={target_sec:.3f},atrim=0:{target_sec:.3f},asetpts=N/SR/TB",
            "-c:a",
            "aac",
            "-b:a",
            _aac_bitrate(),
            str(output_path),
        ],
        stage="video_editor",
        timeout_sec=settings.stage_timeout_sec,
    )
    return output_path


def assemble_video(
    clips: list[Path],
    narration_path: Path,
    output_path: Path,
    subtitles_path: Path | None = None,
    bgm_path: str | None = None,
    playback_speed: float | None = None,
    profile: str = "reel",
    youtube_clips_preformatted: bool = False,
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
        "-crf",
        str(max(15, min(28, int(settings.video_concat_crf)))),
        "-preset",
        str(settings.video_concat_preset or "medium"),
        "-pix_fmt",
        "yuv420p",
        str(merged_video),
    ]
    run_ffmpeg(concat_cmd, stage="video_editor", timeout_sec=settings.stage_timeout_sec)

    prepared_video = merged_video
    if abs(speed - 1.0) > 1e-6 or profile.lower() == "youtube":
        speed_video = output_path.parent / f"video_prepared_{profile}.mp4"
        if profile.lower() == "youtube":
            if youtube_clips_preformatted:
                # Clips already 1920×1080 (panel clips); grade only — avoid double letterbox.
                vf = "eq=contrast=1.03:saturation=1.05,unsharp=5:5:0.5:3:3:0.0"
            else:
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
                "-crf",
                str(max(15, min(28, int(settings.video_concat_crf)))),
                "-preset",
                str(settings.video_concat_preset or "medium"),
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
                _atempo_filter(speed),
                "-c:a",
                "aac",
                "-b:a",
                _aac_bitrate(),
                str(prepared_audio),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
    else:
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(narration_path),
                "-c:a",
                "aac",
                "-b:a",
                _aac_bitrate(),
                str(prepared_audio),
            ],
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
                "-b:a",
                _aac_bitrate(),
                str(mixed_audio),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
        prepared_audio = mixed_audio

    prepared_audio_sync = output_path.parent / "narration_sync.m4a"
    prepared_audio = _fit_audio_to_video_duration(prepared_audio, prepared_video, prepared_audio_sync)

    sub_for_mux: Path | None = None
    if subtitles_path and subtitles_path.exists() and abs(speed - 1.0) > 1e-6:
        sub_for_mux = output_path.parent / f"subtitles_scaled_{profile}.srt"
        scale_srt_for_playback_speed(Path(subtitles_path), speed, sub_for_mux)
    elif subtitles_path and subtitles_path.exists():
        sub_for_mux = Path(subtitles_path)

    mux_cmd = ["ffmpeg", "-y", "-i", str(prepared_video), "-i", str(prepared_audio)]
    if sub_for_mux is not None:
        mux_cmd.extend(["-i", str(sub_for_mux)])
    mux_cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
    )
    if sub_for_mux is not None:
        mux_cmd.extend(["-map", "2:0", "-c:s", "mov_text"])
    mux_cmd.extend(
        [
            # Stream copy: concat (and optional speed/grade pass) already encoded H.264; re-encoding
            # here only hurt quality (generational loss). Soft subs mux fine with copy.
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            _aac_bitrate(),
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
            "-b:a",
            _aac_bitrate(),
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
                "-crf",
                str(max(15, min(28, int(settings.video_concat_crf)))),
                "-preset",
                str(settings.video_concat_preset or "medium"),
                "-c:a",
                "aac",
                "-b:a",
                _aac_bitrate(),
                "-movflags",
                "+faststart",
                str(out),
            ],
            stage="video_editor",
            timeout_sec=settings.stage_timeout_sec,
        )
        chunks.append(out)
    return chunks


def create_reel_derivative(source_video: Path, output_video: Path, playback_speed: float | None = None) -> Path:
    speed = max(0.25, min(4.0, float(playback_speed if playback_speed is not None else settings.reel_playback_speed)))
    vf = (
        f"scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2,"
        "eq=contrast=1.03:saturation=1.05"
    )
    if abs(speed - 1.0) > 1e-6:
        vf += f",setpts=PTS/{speed}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-filter:v",
        vf,
        "-filter:a",
        _atempo_filter(speed),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        _aac_bitrate(),
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    run_ffmpeg(cmd, stage="video_editor", timeout_sec=settings.stage_timeout_sec)
    return output_video
