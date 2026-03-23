from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.utils.ffmpeg_runner import run_ffmpeg

logger = logging.getLogger(__name__)

# FFmpeg 8+ (e.g. Homebrew) may reject `-loop 1` on image inputs ("Option loop not found").
# Use the loop *filter* so a single still frame can be extended for `-t` duration (no input flags).
_STILL_LOOP = "loop=loop=-1:size=1:start=0"

# YouTube landscape motion presets (rotate via PANEL_YOUTUBE_MOTION_ROTATION).
YOUTUBE_MOTION_PRESETS = frozenset({"center_zoom_out", "ken_burns", "static", "slow_drift"})


def _normalize_youtube_motion(name: str | None) -> str:
    n = (name or "center_zoom_out").strip().lower()
    return n if n in YOUTUBE_MOTION_PRESETS else "center_zoom_out"


def _fill_ratio() -> float:
    v = float(getattr(settings, "panel_screen_fill_ratio", 0.92) or 0.92)
    return max(0.5, min(1.0, v))


def _fade_edges(duration: float) -> tuple[float, float]:
    """Return (fade_seconds, fade_out_start_sec)."""
    cap = float(getattr(settings, "panel_transition_fade_sec", 0.15) or 0.15)
    f = min(cap, max(0.02, duration / 3.0))
    out_st = max(0.0, duration - f)
    return f, out_st


def _ken_burns_zoom_in_out_expr(z_peak: float, n_frames: int) -> str:
    """
    One cycle per clip: zoom 1.0 → z_peak (middle) → 1.0 using sin(π·t).
    ``z_peak`` comes from settings (e.g. 1.09 = +9% zoom at the peak).
    """
    z_peak = max(1.0, min(1.4, float(z_peak)))
    amp = z_peak - 1.0
    amp_s = f"{amp:.6f}".rstrip("0").rstrip(".") or "0"
    return f"1+{amp_s}*sin(PI*on/{n_frames})"


def _youtube_zoom_center_to_full_expr(z_peak: float, n_frames: int) -> str:
    """
    YouTube: start **zoomed in on the center** (``z_peak``), ease out to **full panel** (z=1) by the
    end of the clip. Time base uses ``on/(n_frames-1)`` so longer panels (more audio / screen time)
    get a **longer** zoom-out in seconds — the motion naturally scales with duration.
    """
    z_peak = max(1.0, min(1.22, float(z_peak)))
    nm = max(1, int(n_frames) - 1)
    zp = f"{z_peak:.6f}".rstrip("0").rstrip(".")
    # z(0)=z_peak, z(end)=1; smooth ease via cosine half-rise
    return f"{zp}-({zp}-1)*(1-cos(PI*on/{nm}))/2"


def _ken_burns_center_pan_exprs(amp_x: int, amp_y: int, n_frames: int) -> tuple[str, str]:
    """
    Pan drifts around center; strength scales with the same breath as zoom-in-out so movement
    peaks when zoom is strongest (mid panel).
    """
    br = f"sin(PI*on/{n_frames})"
    xf = f"iw/2-(iw/zoom/2)+{amp_x}*{br}*sin(2*PI*on/{n_frames})"
    yf = f"ih/2-(ih/zoom/2)+{amp_y}*{br}*cos(2*PI*on/{n_frames})"
    return xf, yf


def _youtube_center_pan_exprs(amp_x: int, amp_y: int, n_frames: int) -> tuple[str, str]:
    """Pan strongest when zoomed in; fades as we zoom out to full panel (same nm as zoom)."""
    nm = max(1, int(n_frames) - 1)
    br = f"(1+cos(PI*on/{nm}))/2"
    xf = f"iw/2-(iw/zoom/2)+{amp_x}*{br}*sin(2*PI*on/{n_frames})"
    yf = f"ih/2-(ih/zoom/2)+{amp_y}*{br}*cos(2*PI*on/{n_frames})"
    return xf, yf


def _youtube_motion_zoom_pan(
    preset: str,
    inner_w: int,
    inner_h: int,
    n_frames: int,
    amp_x: int,
    amp_y: int,
    zf: float,
) -> tuple[str, str, str, bool]:
    """
    Returns (zoom_expr, xf, yf, use_zoompan). When use_zoompan is False, fg is static (fit + pad only).
    """
    p = _normalize_youtube_motion(preset)
    if p == "static":
        return "", "", "", False
    if p == "ken_burns":
        ze = _ken_burns_zoom_in_out_expr(zf, n_frames)
        xf, yf = _ken_burns_center_pan_exprs(amp_x, amp_y, n_frames)
        return ze, xf, yf, True
    if p == "slow_drift":
        zf2 = max(1.0, min(1.18, zf * 1.02))
        amp_x2 = int(max(10, min(90, amp_x * 12 // 10)))
        amp_y2 = int(max(14, min(95, amp_y * 12 // 10)))
        ze = _youtube_zoom_center_to_full_expr(zf2 * 0.98, n_frames)
        xf, yf = _youtube_center_pan_exprs(amp_x2, amp_y2, n_frames)
        return ze, xf, yf, True
    # center_zoom_out (default)
    ze = _youtube_zoom_center_to_full_expr(zf, n_frames)
    xf, yf = _youtube_center_pan_exprs(amp_x, amp_y, n_frames)
    return ze, xf, yf, True


def _animate_youtube_landscape(
    panel_image: str,
    duration: float,
    output_path: Path,
    *,
    motion: bool,
    motion_preset: str = "center_zoom_out",
) -> None:
    """
    1920×1080 YouTube: sharp panel in safe box; optional **blurred full-frame** background (recap style).

    Motion presets: center_zoom_out, ken_burns, static, slow_drift (rotate via PANEL_YOUTUBE_MOTION_ROTATION).
    """
    fps = max(1, int(settings.default_fps))
    n_frames = max(3, int(round(duration * fps)))
    w_t = int(settings.youtube_target_width)
    h_t = int(settings.youtube_target_height)
    fill = _fill_ratio()
    inner_w = max(320, int(round(w_t * fill)))
    inner_h = max(180, int(round(h_t * fill)))
    f_in, f_out_st = _fade_edges(duration)

    mscale = float(getattr(settings, "panel_youtube_motion_amp_scale", 0.62) or 0.62)
    mscale = max(0.2, min(1.2, mscale))
    amp_y = int(max(14, min(78, inner_h // 20)) * mscale)
    amp_x = int(max(10, min(56, inner_w // 28)) * mscale)
    zf = float(getattr(settings, "panel_youtube_ken_burns_zoom", 1.09) or 1.09)
    zf = max(1.0, min(1.22, zf))

    preset = _normalize_youtube_motion(motion_preset if motion else "static")
    if not motion:
        preset = "static"

    zoom_expr, xf, yf, use_zoompan = _youtube_motion_zoom_pan(
        preset, inner_w, inner_h, n_frames, amp_x, amp_y, zf
    )

    blur_on = bool(getattr(settings, "panel_youtube_blur_background_enabled", True))
    sigma = float(getattr(settings, "panel_youtube_blur_background_sigma", 26.0) or 26.0)
    sigma = max(4.0, min(80.0, sigma))
    dim = float(getattr(settings, "panel_youtube_blur_background_brightness", 0.0) or 0.0)
    dim = max(0.0, min(0.45, dim))
    eq_bg = f",eq=brightness=-{dim:.3f}" if dim > 1e-6 else ""

    # --- Foreground: letterbox with **transparent** pad (RGBA) so blurred bg shows at sides; no black bars.
    if use_zoompan:
        fg_inner = (
            f"[fg0]scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease,format=rgba,"
            f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"zoompan=z='{zoom_expr}':d={n_frames}:"
            f"x='{xf}':"
            f"y='{yf}':"
            f"s={inner_w}x{inner_h}:fps={fps},format=rgba[fg]"
        )
    else:
        fg_inner = (
            f"[fg0]scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease,format=rgba,"
            f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"fps={fps},format=rgba[fg]"
        )

    if blur_on:
        fc = (
            f"[0:v]{_STILL_LOOP},split=2[sg][fg0];"
            f"[sg]scale={w_t}:{h_t}:force_original_aspect_ratio=increase,crop={w_t}:{h_t},"
            f"gblur=sigma={sigma:.3f}{eq_bg},format=yuv420p,setsar=1[bg];"
            f"{fg_inner};"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,format=yuv420p,setsar=1[comp];"
            f"[comp]fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
            f"fps={fps},format=yuv420p"
        )
        command = [
            "ffmpeg",
            "-y",
            "-i",
            panel_image,
            "-t",
            f"{duration:.3f}",
            "-filter_complex",
            fc,
            "-r",
            str(fps),
            str(output_path),
        ]
    else:
        if use_zoompan:
            vf = (
                f"{_STILL_LOOP},"
                f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease,"
                f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2,"
                f"zoompan=z='{zoom_expr}':d={n_frames}:"
                f"x='{xf}':"
                f"y='{yf}':"
                f"s={inner_w}x{inner_h}:fps={fps},"
                f"pad={w_t}:{h_t}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
                f"fps={fps},format=yuv420p"
            )
        else:
            vf = (
                f"{_STILL_LOOP},"
                f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease,"
                f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2,"
                f"pad={w_t}:{h_t}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
                f"fps={fps},format=yuv420p"
            )
        command = [
            "ffmpeg",
            "-y",
            "-i",
            panel_image,
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            str(output_path),
        ]
    run_ffmpeg(command, stage="panel_animator", timeout_sec=settings.stage_timeout_sec)


def _animate_reel_full_bleed(panel_image: str, duration: float, output_path: Path) -> None:
    """
    1080×1920 Shorts/Reels: scale to **cover** full frame (center crop), no letterboxing.

    Tall webtoon panels fill the phone width; narrow strips crop left/right. Optional Ken Burns:
    zoom in then out + X/Y pan (``PANEL_REEL_ZOOM_MOTION``).
    """
    fps = max(1, int(settings.default_fps))
    n_frames = max(3, int(round(duration * fps)))
    tw = int(settings.target_width)
    th = int(settings.target_height)
    mscale = float(getattr(settings, "panel_reel_motion_amp_scale", 0.85) or 0.85)
    mscale = max(0.3, min(1.5, mscale))
    amp_y = int(max(20, min(140, th // 13)) * mscale)
    amp_x = int(max(16, min(110, tw // 10)) * mscale)
    f_in, f_out_st = _fade_edges(duration)
    zf = float(getattr(settings, "panel_reel_ken_burns_zoom", 1.10) or 1.10)
    zf = max(1.0, min(1.28, zf))
    zoom_expr = _ken_burns_zoom_in_out_expr(zf, n_frames)
    xf, yf = _ken_burns_center_pan_exprs(amp_x, amp_y, n_frames)
    motion = bool(getattr(settings, "panel_reel_zoom_motion", True))

    # Cover + center crop to exact 9:16, then optional zoompan on the full frame.
    base = (
        f"{_STILL_LOOP},"
        f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th}:(iw-{tw})/2:(ih-{th})/2"
    )
    if motion:
        vf = (
            f"{base},"
            f"zoompan=z='{zoom_expr}':d={n_frames}:"
            f"x='{xf}':"
            f"y='{yf}':"
            f"s={tw}x{th}:fps={fps},"
            f"fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
            f"fps={fps},format=yuv420p"
        )
    else:
        vf = (
            f"{base},"
            f"fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
            f"fps={fps},format=yuv420p"
        )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        panel_image,
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-r",
        str(fps),
        str(output_path),
    ]
    run_ffmpeg(command, stage="panel_animator", timeout_sec=settings.stage_timeout_sec)


def _animate_reel_legacy(panel_image: str, duration: float, output_path: Path) -> None:
    """Letterboxed portrait with ~90% inner content area."""
    fps = max(1, int(settings.default_fps))
    tw = int(settings.target_width)
    th = int(settings.target_height)
    fill = _fill_ratio()
    inner_w = max(360, int(round(tw * fill)))
    inner_h = max(640, int(round(th * fill)))
    f_in, f_out_st = _fade_edges(duration)
    vf = (
        f"{_STILL_LOOP},"
        f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease,"
        f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,"
        f"fade=t=in:st=0:d={f_in:.3f},fade=t=out:st={f_out_st:.3f}:d={f_in:.3f},"
        f"fps={fps},format=yuv420p"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        panel_image,
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-r",
        str(fps),
        str(output_path),
    ]
    run_ffmpeg(command, stage="panel_animator", timeout_sec=settings.stage_timeout_sec)


def animate_panel(
    panel_image: str,
    duration: float,
    output_path: Path,
    profile: str = "youtube",
    *,
    youtube_motion: str | None = None,
) -> Path:
    """
    Render one panel clip.

    - ``youtube``: 1920×1080 — full panel + optional blurred backdrop; motion presets via ``youtube_motion``
      or ``PANEL_YOUTUBE_MOTION_ROTATION`` on the timeline entry.
    - ``reel``: 1080×1920 — full-bleed cover crop (Shorts/TikTok style); motion when ``PANEL_REEL_ZOOM_MOTION`` is on.
    """
    prof = (profile or "youtube").strip().lower()
    motion_yt = getattr(settings, "panel_youtube_zoom_motion", True)
    yt_preset = (youtube_motion or "center_zoom_out").strip().lower()
    try:
        if prof == "youtube":
            _animate_youtube_landscape(
                panel_image,
                duration,
                output_path,
                motion=motion_yt,
                motion_preset=yt_preset,
            )
        elif prof == "reel":
            if getattr(settings, "panel_reel_full_bleed", True):
                _animate_reel_full_bleed(panel_image, duration, output_path)
            else:
                _animate_reel_legacy(panel_image, duration, output_path)
        else:
            logger.warning("animate_panel unknown profile=%s; using youtube", prof)
            _animate_youtube_landscape(
                panel_image,
                duration,
                output_path,
                motion=motion_yt,
                motion_preset=yt_preset,
            )
    except Exception as exc:
        logger.warning("animate_panel profile=%s fallback (%s)", prof, exc)
        if prof == "reel":
            _animate_reel_legacy(panel_image, duration, output_path)
        else:
            _animate_youtube_landscape(panel_image, duration, output_path, motion=False, motion_preset="static")
    return output_path
