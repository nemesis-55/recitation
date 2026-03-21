# Manga Video Pipeline - Detailed Documentation

## Overview

`manga_video_pipeline` converts manga sources into vertical recitation videos with subtitles.

Supported input sources:
- Local PDF path
- Webtoon episode URL

High-level output:
- `video.mp4` (final recitation video)
- `subtitles.srt` (subtitle file)
- `job_report.json` (stage-level execution report)

---

## End-to-End Flow

1. `preflight`
   - Validates required keys, provider config, and disk space.
2. `pdf_loader` or `webtoon_loader`
   - Loads source pages/panels depending on input type.
3. `panel_extractor` (PDF only)
   - Extracts panel images from page images.
4. `ocr_engine`
   - Uses OpenAI for OCR extraction from panel images.
5. `script_cleaner`
   - Converts noisy OCR text into structured dialogue metadata.
6. `narrator`
   - Synthesizes line-level TTS and merged narration audio.
7. `timeline_builder`
   - Builds panel timeline durations based on audio timing.
8. `panel_animator`
   - Creates animated per-panel clips.
9. `subtitle_generator`
   - Generates SRT from timeline narration.
10. `video_editor`
    - Concatenates clips, merges audio, applies speed/subtitles.
11. `quality_checker`
    - Confirms video/audio streams and quality gates.

---

## Source Types and Run Paths

Runs are stored under:
- `outputs/runs/<run_key>/`

For Webtoon URLs, run keys are nested:
- `outputs/runs/<genre>/<title>/<episode>/`
- Example: `outputs/runs/romance/dirty-deeds/episode-1`

If a run key already exists, suffixes are appended:
- `episode-1_2`, `episode-1_3`, etc.

---

## Run Folder Structure

Typical run tree:

```text
outputs/runs/<run_key>/
  pages/        # PDF page images (if PDF input)
  panels/       # Extracted/downloaded panel images
  audio/        # line_*.mp3 + narration.mp3
  clips/        # clip_*.mp4
  final/        # video.mp4, subtitles.srt, merged.mp4, concat.txt
  meta/         # timeline.json, job_report.json
```

---

## Dialogue and Metadata Model

`script_cleaner` normalizes OCR into one structured line per OCR panel item.

`ScriptLine` fields:
- `panel_path`: source panel image path
- `narration`: cleaned line text
- `speaker`: one of `male_1`, `male_2`, `female_1`, `female_2`, `narrator`, `unknown_1`
- `gender`: `male`, `female`, `unknown`
- `emotion`: `angry`, `sad`, `fear`, `happy`, `neutral`
- `voice`: selected TTS voice used for synthesis

Normalization rules include:
- Strict enum enforcement for `speaker`, `gender`, `emotion`
- Order-preserving one-row-per-input behavior
- Filler suppression for non-semantic vocalizations (for example repeated `huuu`/`haaa`)

---

## Voice Acting Engine (Audio-First)

The TTS layer supports dynamic per-line voice assignment and provider fallback:
- Narrator lines use narrator voice
- Gender-based assignment for male/female
- Unknown-gender lines can alternate between male/female reciter voices
- Emotion overrides can map specific emotions to preferred voices
- Emotion intensity (`0..1`) is estimated from punctuation/casing patterns
- Rendered speech text is produced before TTS (fear hesitation, sad trailing, angry emphasis)
- Emotion-aware pause engine inserts per-line pacing and serializes audio timeline metadata

Provider behavior:
- Auto mode follows `TTS_PROVIDER_ORDER` (default `elevenlabs`)
- `TTS_PROVIDER` is fixed to ElevenLabs for narration (`elevenlabs`)
- Retry logic with provider timeout and retries
- Binary audio cache reuse when enabled

Important environment knobs:
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_API_BASE_URL`
- `ELEVENLABS_TTS_MODEL`
- `ELEVENLABS_VOICE_MALE`
- `ELEVENLABS_VOICE_FEMALE`
- `ELEVENLABS_VOICE_UNKNOWN`
- `ELEVENLABS_VOICE_NARRATOR`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `OPENAI_TTS_VOICE_MALE`
- `OPENAI_TTS_VOICE_FEMALE`
- `OPENAI_TTS_VOICE_UNKNOWN`
- `OPENAI_TTS_VOICE_NARRATOR`
- `OPENAI_TTS_EMOTION_OVERRIDES`
- `TTS_PROVIDER`
- `TTS_PROVIDER_ORDER`

---

## Sync Strategy

Sync is enforced in multiple layers:

1. Timeline uses audio duration as source-of-truth when segment audio exists.
2. Panels with no text/audio get minimum hold duration to avoid fast visual skipping.
3. Final assembly merges timeline-derived clips with narration, then applies shared speed factor.
4. Quality check verifies streams, duration bounds, and A/V delta metric (`av_delta_sec`).

If you observe drift:
- Compare stream durations with `ffprobe`
- Inspect `meta/timeline.json` and `audio/narration.mp3`
- Rebuild final stage using existing run artifacts

---

## Caching

Cache root:
- `outputs/cache/`

Namespaces used:
- `ocr_engine` (panel OCR result cache)
- `script_cleaner_chunks` (chunk-level dialogue cleaning cache)
- `script_cleaner` (full cleaned script cache)
- `tts_audio` (voice-aware binary TTS cache)

Disable cache:
- `ENABLE_CACHE=false`

---

## API Endpoints

Core:
- `POST /generate`

Ops:
- `GET /ops`
- `GET /ops/api/runs`
- `GET /ops/api/runs/{run_path}`
- `GET /ops/api/runs/{run_path}/video`
- `POST /ops/api/generate`

Notes:
- `run_path` supports nested keys (`romance/dirty-deeds/episode-1`)
- Ops UI supports run filtering, pagination, deep-linking (`?run_id=...`), and inline media preview

---

## Key Environment Variables

Core:
- `OPENAI_API_KEY`
- `RUNWAY_API_KEY`
- `ELEVENLABS_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TTS_MODEL`
- `TTS_PROVIDER`
- `PROVIDER_TIMEOUT_SEC`
- `PROVIDER_RETRIES`
- `AV_SYNC_MAX_DELTA_SEC`

OCR:
- `OPENAI_OCR_BATCH_SIZE`
- `OPENAI_OCR_MAX_IMAGE_DIM`
- `OPENAI_OCR_JPEG_QUALITY`
- `OPENAI_OCR_RECOVERY_BATCHES`

Pipeline behavior:
- `MIN_PANEL_DURATION_SEC`
- `MAX_PANEL_DURATION_SEC`
- `MIN_VIDEO_DURATION_SEC`
- `MAX_VIDEO_DURATION_SEC`
- `ENABLE_SUBTITLES_DEFAULT`
- `STAGE_TIMEOUT_SEC`
- `ENABLE_CACHE`

---

## Troubleshooting Guide

### 1) Input Not Found
- Error examples: `PDF_NOT_FOUND`, webtoon fetch/download errors
- Check input path/URL and network access

### 2) Provider Failures
- Error examples: `OPENAI_RATE_LIMITED`, `OPENAI_AUTH_FAILED`, `OPENAI_TTS_FAILED`
- Verify API keys and reduce OCR batch size
- Enable debug logs with `OPENAI_DEBUG_IO=true` for diagnosis

### 3) Subtitle Burn Failure
- If FFmpeg lacks subtitle filter support, fallback to embedded subtitle track is used

### 4) Audio/Video Drift
- Regenerate using existing run artifacts
- Confirm both streams after final build:
  - `ffprobe -show_entries stream=index,codec_type,duration`

### 5) Unnatural Fillers in Narration
- Check `script_cleaner` normalization and cached TTS lines
- Clear `outputs/cache/tts_audio` for fresh synthesis

---

## Testing and QA

Run test suite:

```bash
python3 -m pytest -q
```

Recommended smoke workflow:
1. Run one short Webtoon generation (`max_panels` small).
2. Inspect `meta/job_report.json`.
3. Preview final video via Ops UI.
4. Verify stream durations with `ffprobe`.

---

## Security Notes

- Never commit real API keys in `.env`.
- Rotate keys immediately if exposed.
- Keep run artifacts out of public repos unless intentionally shared.
