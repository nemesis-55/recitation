# Manga Video Pipeline

Production-oriented pipeline that converts a manga PDF into a vertical cinematic recitation video.

Detailed technical guide: see [`DETAILED_DOCUMENTATION.md`](DETAILED_DOCUMENTATION.md).

## Features

- End-to-end flow: PDF -> pages -> panels -> OCR -> OpenAI script cleaning -> ElevenLabs TTS -> panel animation -> timeline -> subtitles -> final video.
- Strict fail-fast provider policy: if OpenAI or ElevenLabs fails, job stops with structured error.
- Vertical output (`1080x1920`) with Ken Burns style motion from original manga panels only.
- Stage artifacts and job report under `outputs/runs/<run_key>/`.
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
- FFmpeg and FFprobe installed in PATH
- Poppler installed (required by `pdf2image`)
- OpenAI and ElevenLabs API keys

## Environment

Create `.env` in repo root:

```env
OPENAI_API_KEY=your_openai_key
ELEVENLABS_API_KEY=your_elevenlabs_key
LOG_LEVEL=INFO
```

Optional knobs:

```env
MAX_PAGES=80
MIN_VIDEO_DURATION_SEC=30
MAX_VIDEO_DURATION_SEC=180
ENABLE_SUBTITLES_DEFAULT=true
```

## Install

```bash
pip install -r manga_video_pipeline/requirements.txt
```

## Run API

```bash
uvicorn app.main:app --reload --app-dir manga_video_pipeline
```

## Operations UI

- Open `http://127.0.0.1:8000/ops` for the operations dashboard.
- Features:
  - start generation jobs
  - monitor recent runs
  - inspect per-run reports and output artifacts

## Generate Video

`POST /generate`

Request:

```json
{
  "pdf_path": "/absolute/path/to/manga.pdf",
  "subtitles": true
}
```

You can also pass a Webtoon episode URL in `pdf_path`:

```json
{
  "pdf_path": "https://www.webtoons.com/en/.../episode/viewer?title_no=123&episode_no=45",
  "subtitles": true
}
```

For Webtoon URLs, the pipeline auto-downloads ordered panel images from `img._images[data-url]` and continues with OCR, narration, animation, and final assembly.

Success response:

```json
{
  "status": "completed",
  "video_path": "manga_video_pipeline/outputs/runs/<run_key>/final/video.mp4"
}
```

Fail response:

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

- No default provider fallback is used.
- If OpenAI or ElevenLabs errors, pipeline aborts immediately.
- Each stage emits structured logs and timing data.
- A `job_report.json` is generated per run for troubleshooting.
- Ops API supports nested run keys (example: `romance/dirty-deeds/episode-1`) in run-detail routes.
- Ops dashboard includes search/filter/pagination, deep-linking (`?run_id=...`), and inline final video preview.

## Testing

```bash
pytest -q manga_video_pipeline/tests
```
