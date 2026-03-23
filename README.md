# Manga Video Pipeline (SRT-Driven Cinematic Audio)

Pipeline for building vertical manga recap videos with **SRT as the master timeline** and cinematic audio generation.

Detailed technical guide: [`DETAILED_DOCUMENTATION.md`](DETAILED_DOCUMENTATION.md).

## What It Does

- Input: manga source (`pdf_path` or webtoon URL). Optional `srt_path` can be provided as master timeline; otherwise timeline is auto-generated from OCR.
- Audio flow: SRT → OpenAI dialogue analysis → deterministic speech rendering → ElevenLabs TTS (grouped lines) → optional SFX/music → cinematic FFmpeg mix; **scene bed** can use ElevenLabs music or the **local BGM library** (`outputs/cache/bgm_library`) when configured.
- Video flow: panels are animated using SRT durations, then muxed with narration and subtitles.
- Provider failures are **fatal** for TTS; music can **fall back** to the local BGM library or `BGM_DEFAULT_PATH` when ElevenLabs music is off.

**Lower cost (no code changes):** see [`docs/COST_SAVINGS.md`](docs/COST_SAVINGS.md) and copy [`/.env.example`](.env.example) as a starting point.

## Project Layout

```text
manga_video_pipeline/
  app/
    main.py
    config.py
    routes/generate.py
    services/
    utils/
    models/
  outputs/
  tests/
  requirements.txt
```

## Preview panel motion (Ken Burns samples)

Without running a full episode, render short **YouTube** + **Reel** clips using your `PANEL_*` settings:

```bash
cd manga_video_pipeline
python scripts/render_ken_burns_sample.py
# → outputs/samples/sample_youtube_ken_burns.mp4
# → outputs/samples/sample_reel_ken_burns.mp4
```

Optional: `python scripts/render_ken_burns_sample.py --panel /path/to/panel.jpg --duration 2.5`

## Rebuild YouTube video from a run folder (test new panel look)

After changing blur/motion settings, regenerate **only** the video from existing `panels/` + `meta/timeline.json` + `audio/narration.mp3` (no API calls):

```bash
cd manga_video_pipeline
python scripts/rebuild_youtube_from_run.py --run-dir outputs/runs/action/a-flame-reborn/episode-1
# → final/video_youtube_rebuild.mp4

# Quick smoke test (first 3 panels only)
python scripts/rebuild_youtube_from_run.py --run-dir outputs/runs/.../episode-1 --max-panels 3
```

## Prerequisites

- Python 3.10+
- FFmpeg and FFprobe in `PATH`
- Poppler (for PDF input)
- OpenAI API key (dialogue analysis)
- ElevenLabs API key (TTS + SFX + Music; optional STS)

## Environment

Create `.env` in the **repo root** or under `manga_video_pipeline/` (both are loaded). Reference template: [`.env.example`](.env.example).

**Cost tuning:** [`docs/COST_SAVINGS.md`](docs/COST_SAVINGS.md) (cache, emotion refine, EL music/SFX, OCR size, TTS grouping).

**Required for real runs:**

```env
OPENAI_API_KEY=your_openai_key
ELEVENLABS_API_KEY=your_elevenlabs_key
LOG_LEVEL=INFO
```

**Common optional knobs:**

```env
# Video
VIDEO_PLAYBACK_SPEED=1.2
REEL_PLAYBACK_SPEED=1.2
RUN_KEEP_INTERMEDIATE_CLIPS=false

# SRT master timeline
SRT_REQUIRE_INPUT=true

# BGM in final mux
BGM_DEFAULT_PATH=/absolute/path/to/bed.mp3
BGM_VOLUME=0.14

# Local BGM library (default: outputs/cache/bgm_library, 10 slots bgm_00.mp3 … bgm_09.mp3)
# Lazy-filled: ElevenLabs music (if enabled), else copy of BGM_DEFAULT_PATH, else FFmpeg tone.
# Slot choice follows dominant dialogue emotion → one of 10 mood families; BGM_LIBRARY_COUNT>10
# adds variant takes (bgm_10+ same style cycle as bgm_00…09), not unrelated random beds.
# When BGM_LIBRARY_PREFER_LOCAL=true (default), narration uses the library before per-scene EL music.
#BGM_LIBRARY_DIR=
BGM_LIBRARY_COUNT=10
BGM_LIBRARY_PREFER_LOCAL=true

# Smoother multi-scene narration stitch (subtitles stay aligned; 0 = off)
#AUDIO_SCENE_CROSSFADE_SEC=0.06

# Video panel concat + final AAC bitrate (libx264 + aac)
#VIDEO_CONCAT_CRF=20
#VIDEO_CONCAT_PRESET=medium
#VIDEO_MUX_AUDIO_BITRATE_K=192

# Cinematic narration mix
AUDIO_BED_IN_NARRATION=true
AUDIO_MIXER_DUCKING_ENABLED=true
AUDIO_MIXER_MUSIC_GAIN=0.16
# Music bed only: reduce mud vs voice; 0 disables. Does not change narration timing/sync.
AUDIO_MIXER_MUSIC_HIGHPASS_HZ=100
AUDIO_MIXER_MUSIC_DYNAUDNORM_ENABLED=true
AUDIO_MIXER_SFX_GAIN=0.7
AUDIO_MIXER_VOICE_GAIN=1.0

# ElevenLabs generation
ELEVENLABS_SFX_ENABLED=true
ELEVENLABS_MUSIC_ENABLED=true
ELEVENLABS_STS_ENABLED=false

# TTS: more natural / less flat (defaults are tuned for human-like prosody)
ELEVENLABS_TTS_HUMANIZE=true
ELEVENLABS_TTS_SPEECH_SPEED=0.97
ELEVENLABS_TTS_LINE_CONTEXT=true
ELEVENLABS_TTS_OPTIMIZE_STREAMING_LATENCY=0
# Model: flash is fast; try eleven_multilingual_v2 or eleven_turbo_v2_5 if you want warmer delivery.
# ELEVENLABS_TTS_MODEL=eleven_flash_v2_5

# Per-speaker ElevenLabs voice IDs (JSON)
ELEVENLABS_VOICE_MAP_JSON=

# Pipeline
MAX_PAGES=80
MIN_VIDEO_DURATION_SEC=30
MAX_VIDEO_DURATION_SEC=180
ENABLE_SUBTITLES_DEFAULT=true
ENABLE_CACHE=true
```

## Install

```bash
pip install -r manga_video_pipeline/requirements.txt
```

## Run API

From the `manga_video_pipeline` directory (so `app` resolves):

```bash
cd manga_video_pipeline
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or from the repo root:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir manga_video_pipeline
```

## Operations UI

- Open `http://127.0.0.1:8000/ops` for the operations dashboard.
- Start jobs, browse runs, inspect `job_report.json`, preview `video.mp4`.
- Search local Webtoon catalog by genre/title and generate episode ranges sequentially.
- Refresh catalog index from crawler using the UI button.

## Generate Video (`POST /generate`)

```json
{
  "pdf_path": "/absolute/path/to/manga.pdf",
  "srt_path": "/absolute/path/to/subtitles.srt"
}
```

**Success:**

```json
{
  "status": "completed",
  "video_path": "manga_video_pipeline/outputs/runs/<run_key>/final/video.mp4",
  "audio_path": "manga_video_pipeline/outputs/runs/<run_key>/audio/narration.mp3",
  "quality": "cinematic"
}
```

**Failure:**

```json
{
  "status": "failed",
  "stage": "srt_loader",
  "error_code": "SRT_REQUIRED",
  "error": "..."
}
```

## Operational Notes

- `script_cleaner` has been removed from runtime; OCR-derived timeline drives narration timing.
- ElevenLabs SFX/Music/TTS failures are surfaced as provider errors and stop the run.
- `meta/job_report.json` includes `srt_analysis` and `audio_event_timeline`.
- OCR timeline generation is enabled by default; `srt_path` is optional.

## Webtoon Catalog + Episode Range

New ops APIs:

- `GET /ops/api/manga` — searchable local catalog
- `GET /ops/api/manga/{title_slug}/episodes` — episodes for selected title
- `GET /ops/api/manga/status` — catalog refresh status
- `POST /ops/api/manga/refresh` — manual crawl refresh
- `POST /ops/api/generate-range` — sequential per-episode generation

Startup behavior:

- If `WEBTOON_CATALOG_ENABLED=true`, the app performs a **blocking** catalog refresh at startup.
- Startup serves requests only after refresh is done.

## Testing

See **[`TESTING.md`](TESTING.md)** for layout, scope, and optional debug env.

```bash
cd manga_video_pipeline && python3 -m pytest -q
```

Optional NDJSON diagnostics (audio pipeline / mixer):

```env
PIPELINE_DEBUG_NDJSON_PATH=/tmp/pipeline_debug.ndjson
```

## New Environment Knobs

```env
# Local catalog
WEBTOON_CATALOG_ENABLED=false
WEBTOON_CATALOG_FILE=webtoon_catalog.json
WEBTOON_CATALOG_GENRE_URLS_JSON=["https://www.webtoons.com/en/action", "https://www.webtoons.com/en/romance"]
WEBTOON_CATALOG_REQUEST_TIMEOUT_SEC=25
WEBTOON_CATALOG_MAX_TITLES_PER_GENRE=80
WEBTOON_CATALOG_MAX_EPISODES_PER_TITLE=250

# OpenAI load control
OPENAI_OCR_BATCH_SIZE=3
OPENAI_OCR_BATCH_PACE_SEC=0.35
OPENAI_DIALOGUE_BATCH_SIZE=3
OPENAI_DIALOGUE_BATCH_PACE_SEC=0.35
```
