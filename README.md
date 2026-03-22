# Manga Video Pipeline (SRT-Driven Cinematic Audio)

Pipeline for building vertical manga recap videos with **SRT as the master timeline** and cinematic audio generation.

Detailed technical guide: [`DETAILED_DOCUMENTATION.md`](DETAILED_DOCUMENTATION.md).

## What It Does

- Input: manga source (`pdf_path` or webtoon URL). Timeline is auto-generated from OCR.
- Audio flow: SRT -> OpenAI dialogue analysis -> deterministic speech rendering -> ElevenLabs TTS per line -> ElevenLabs SFX -> ElevenLabs scene music -> cinematic FFmpeg mix.
- Video flow: panels are animated using SRT durations, then muxed with narration and subtitles.
- Provider failures are **fatal** (no local fallback for ElevenLabs SFX/Music/TTS).

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

## Prerequisites

- Python 3.10+
- FFmpeg and FFprobe in `PATH`
- Poppler (for PDF input)
- OpenAI API key (dialogue analysis)
- ElevenLabs API key (TTS + SFX + Music; optional STS)

## Environment

Create `.env` in the **repo root** or under `manga_video_pipeline/` (both are loaded).

**Required for real runs:**

```env
OPENAI_API_KEY=your_openai_key
ELEVENLABS_API_KEY=your_elevenlabs_key
LOG_LEVEL=INFO
```

**Common optional knobs:**

```env
# Video
VIDEO_PLAYBACK_SPEED=1.0
RUN_KEEP_INTERMEDIATE_CLIPS=false

# SRT master timeline
SRT_REQUIRE_INPUT=true

# BGM in final mux
BGM_DEFAULT_PATH=/absolute/path/to/bed.mp3
BGM_VOLUME=0.14

# Cinematic narration mix
AUDIO_BED_IN_NARRATION=true
AUDIO_MIXER_DUCKING_ENABLED=true
AUDIO_MIXER_MUSIC_GAIN=0.16
AUDIO_MIXER_SFX_GAIN=0.7
AUDIO_MIXER_VOICE_GAIN=1.0

# ElevenLabs generation
ELEVENLABS_SFX_ENABLED=true
ELEVENLABS_MUSIC_ENABLED=true
ELEVENLABS_STS_ENABLED=false

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
  "pdf_path": "/absolute/path/to/manga.pdf"
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
- OCR timeline generation is always enabled (no `srt_path` request field).

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

```bash
cd manga_video_pipeline && python3 -m pytest tests/ -q
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
