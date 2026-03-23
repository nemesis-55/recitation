"""
Persisted local background music library: multiple loopable beds (default 10) for reuse
across scenes/episodes without calling ElevenLabs every time.

Files live under ``outputs/cache/bgm_library`` (or ``BGM_LIBRARY_DIR``) as ``bgm_00.mp3`` …
Missing slots are filled lazily: ElevenLabs music (if enabled), else copy ``BGM_DEFAULT_PATH``,
else a short FFmpeg-generated pad so the narration bed is never silently empty.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.config import settings
from app.utils.ffmpeg_runner import run_ffmpeg

# Number of distinct “families” of beds (prompts repeat every N slots: slot 3 vs 13 share style).
BGM_FAMILY_COUNT: int = 10


# Ten distinct instrumental briefs — used when generating library slots via ElevenLabs.
BGM_LIBRARY_SLOT_PROMPTS: list[str] = [
    "Soft neo-classical ambient underscore with airy pads and light strings, loopable, no vocals",
    "Melancholic felt piano with distant cello, emotional cinematic bed, loopable, no vocals",
    "Low pulsing cinematic tension, subtle synth bass and strings, suspense, loopable, no vocals",
    "Warm gentle plucks and soft strings, hopeful undertone, loopable, no vocals",
    "Dark ambient drone with subtle motion, ominous atmosphere, loopable, no vocals",
    "Light investigative pizzicato and soft pulses, curious mystery mood, loopable, no vocals",
    "Epic soft orchestral pads with gentle brass swell, heroic undertone, loopable, no vocals",
    "Sparse intimate piano with airy texture, reflective, loopable, no vocals",
    "Driving subtle percussion loop with low strings, action undertone, loopable, no vocals",
    "Ethereal wide pads and soft shimmer, dreamy cinematic, loopable, no vocals",
]


# Maps dialogue emotion → family index 0..9 matching BGM_LIBRARY_SLOT_PROMPTS order.
# When BGM_LIBRARY_COUNT > 10, only the last digit (slot % 10) selects the style; extra slots are
# alternate takes of the same mood (base + 10, base + 20, …).
_EMOTION_TO_FAMILY: dict[str, int] = {
    "neutral": 0,
    "sad": 1,
    "fear": 2,
    "angry": 8,
    "happy": 3,
    "surprised": 2,
    "curious": 5,
    "confused": 5,
    "determined": 6,
    "hopeful": 3,
    "resigned": 1,
    "pain": 1,
    "concerned": 2,
    "worried": 2,
    "weak": 7,
    "urgent": 8,
    "nostalgic": 7,
    "reassuring": 3,
    "regretful": 1,
    "apologetic": 7,
    "serious": 4,
    "desperate": 2,
    "frustrated": 2,
    "teasing": 5,
    "defensive": 2,
}


def _emotion_family(emotion: str) -> int:
    key = (emotion or "neutral").strip().lower()
    if key in _EMOTION_TO_FAMILY:
        return _EMOTION_TO_FAMILY[key]
    return 0


def bgm_library_root() -> Path:
    raw = getattr(settings, "bgm_library_dir", None)
    if raw:
        return Path(str(raw)).expanduser().resolve()
    pipeline_root = Path(__file__).resolve().parents[3]
    return (pipeline_root / "outputs" / "cache" / "bgm_library").resolve()


def bgm_library_count() -> int:
    n = int(getattr(settings, "bgm_library_count", 10) or 10)
    return max(1, min(64, n))


def pick_bgm_slot(emotion: str, scene_id: int | None, line_count: int) -> int:
    """
    Pick a stable slot 0..count-1.

    Previously: ``hash(emotion|scene|lines) % count`` — with a large library this scattered
    moods across unrelated beds. Now: choose a **mood family** (0..9) from ``emotion``, then pick
    among slots ``family``, ``family+10``, … that exist (variant takes). Hash only breaks ties
    between variants of the **same** family so BGM stays on-brand for the scene.
    """
    count = bgm_library_count()
    family = _emotion_family(emotion) % BGM_FAMILY_COUNT
    eligible = [family + 10 * k for k in range(64) if family + 10 * k < count]
    tie = f"{(emotion or 'neutral').lower()}|{scene_id if scene_id is not None else -1}|{max(0, line_count)}"
    h = hashlib.sha256(tie.encode("utf-8")).hexdigest()
    digest = int(h[:8], 16)
    if eligible:
        return eligible[digest % len(eligible)]
    return digest % max(1, count)


def _is_nonempty_audio(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 512
    except OSError:
        return False


def _synthesize_minimal_bed(output_path: Path, slot: int) -> None:
    """Last-resort loopable tone so mixing never runs fully dry."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Slightly different character per slot (Hz).
    freq = 110.0 + float(slot) * 18.5
    dur = 90.0
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq:.2f}:sample_rate=44100",
            "-t",
            f"{dur:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(output_path),
        ],
        stage="bgm_library",
        timeout_sec=120,
    )


def ensure_bgm_slot(slot: int) -> Path | None:
    """
    Ensure ``bgm_{slot:02d}.mp3`` exists in the library directory and return its path.
    """
    count = bgm_library_count()
    if slot < 0 or slot >= count:
        slot = slot % count
    root = bgm_library_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"bgm_{slot:02d}.mp3"
    if _is_nonempty_audio(target):
        return target

    # 1) ElevenLabs music API (cached under elevenlabs_music inside generate_scene_music)
    if settings.elevenlabs_music_enabled and settings.elevenlabs_api_key:
        try:
            from app.services.audio.music_engine import generate_scene_music  # noqa: PLC0415

            prompt = BGM_LIBRARY_SLOT_PROMPTS[slot % len(BGM_LIBRARY_SLOT_PROMPTS)]
            generate_scene_music(prompt=prompt, duration_ms=120_000, output_path=target)
            if _is_nonempty_audio(target):
                return target
        except Exception:
            pass

    # 2) Copy user default BGM into this slot
    default = settings.bgm_default_path
    if default:
        p = Path(str(default)).expanduser()
        if p.is_file():
            shutil.copy2(p, target)
            if _is_nonempty_audio(target):
                return target

    # 3) FFmpeg minimal bed
    try:
        _synthesize_minimal_bed(target, slot)
        if _is_nonempty_audio(target):
            return target
    except Exception:
        pass

    return None


def materialize_bed_for_scene(slot: int, audio_dir: Path) -> Path | None:
    """Copy library slot into scene dir as ``music_scene.mp3`` for mixing."""
    src = ensure_bgm_slot(slot)
    if src is None or not src.is_file():
        return None
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / "music_scene.mp3"
    shutil.copy2(src, out)
    return out
