# Manga Video Pipeline

Production-oriented pipeline that converts a manga PDF (or Webtoon episode URL) into a vertical cinematic recitation video.

Detailed technical guide: [`DETAILED_DOCUMENTATION.md`](DETAILED_DOCUMENTATION.md).

## Features

- End-to-end flow: PDF/Webtoon → panels → **OpenAI OCR** → **OpenAI script cleaning** → **ElevenLabs TTS only** → panel animation → timeline → subtitles → final video.
- **Optional music bed** under narration: local files / `BGM_DEFAULT_PATH` (no ElevenLabs Music or Sound Generation APIs).
- **Final video at 1× speed by default** (`VIDEO_PLAYBACK_SPEED`); video and narration stay in sync when you change speed.
- **Disk use:** by default, per-panel `clips/` and `final/merged.mp4` + `concat.txt` are removed after a successful run (`RUN_KEEP_INTERMEDIATE_CLIPS=false`).
- Strict fail-fast for required providers: OpenAI or ElevenLabs TTS failures stop the job with a structured error.
- Vertical output (`1080×1920`) with Ken Burns–style motion from original panels.
- Stage artifacts and `job_report.json` under `outputs/runs/<run_key>/`.
- Webtoon runs use nested folders: `outputs/runs/<genre>/<title>/<episode>/`.

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
- Poppler (for `pdf2image`, PDF input only)
- **OpenAI** API key (OCR + script cleaner)
- **ElevenLabs** API key (**text-to-speech only**)

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

# BGM in final mux (see DETAILED_DOCUMENTATION for dedupe with narration bed)
BGM_DEFAULT_PATH=/absolute/path/to/bed.mp3
BGM_VOLUME=0.14

# Narration: optional instrumental bed (local files only)
AUDIO_BED_IN_NARRATION=true
AUDIO_USE_BGM_DEFAULT_AS_BED=true
AUDIO_MUSIC_VOLUME=0.12
# JSON map: emotion -> file path, e.g. {"fear":"/path/tense.mp3","neutral":"/path/soft.mp3"}
AUDIO_MUSIC_LOCAL_MAP_JSON=

# TTS grouping (disable for one API call per line)
AUDIO_GROUPING_ENABLED=true
AUDIO_STRICT_PER_LINE_TTS=false
AUDIO_GROUP_MAX_CHARS=220

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

## Generate Video

`POST /generate`

```json
{
  "pdf_path": "/absolute/path/to/manga.pdf",
  "subtitles": true
}
```

Webtoon episode URL in `pdf_path` is supported; the pipeline downloads ordered panel images and continues as with PDFs.

Optional request fields include `target_duration_sec`, `max_panels`, and `bgm_path` (overrides default BGM for the **final video mux** when set).

**Success:**

```json
{
  "status": "completed",
  "video_path": "manga_video_pipeline/outputs/runs/<run_key>/final/video.mp4"
}
```

**Failure:**

```json
{
  "status": "failed",
  "stage": "script_cleaner",
  "provider": "openai",
  "error_code": "OPENAI_CLEAN_FAILED",
  "error": "..."
}
```

## Operational Notes

- No automatic fallback to a second TTS provider; ElevenLabs is the narration implementation.
- Each stage logs timing; `meta/job_report.json` records stages (including `narration_music_source` when a bed was applied).
- Ops API supports nested run keys (e.g. `romance/dirty-deeds/episode-1`).

## Testing

```bash
cd manga_video_pipeline && python3 -m pytest tests/ -q
```
