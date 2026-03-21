# Manga Video Pipeline — Detailed Documentation

## Overview

`manga_video_pipeline` turns manga sources into vertical recitation videos with optional subtitles.

**Inputs**

- Local PDF path  
- Webtoon episode URL  

**Main outputs**

- `final/video.mp4` — final video  
- `final/subtitles.srt` — when subtitles are enabled  
- `meta/job_report.json` — per-stage report  
- `meta/timeline.json`, `meta/audio_timeline.json` — timing metadata  
- `audio/narration.mp3` — full narration mix (voice + optional bed + optional SFX/ambience)  

---

## End-to-End Flow

1. **preflight** — Keys, disk space, basic config.  
2. **pdf_loader** or **webtoon_loader** — Pages or downloaded panels.  
3. **panel_extractor** (PDF only) — Panel crops.  
4. **ocr_engine** — OpenAI vision OCR per batch.  
5. **script_cleaner** — OCR → structured `ScriptLine`s (OpenAI text).  
6. **narrator** / **audio_pipeline** — Dialogue analysis, ElevenLabs TTS, optional **local** music bed, SFX/ambience, `narration.mp3`.  
7. **timeline_builder** — Panel durations from audio.  
8. **panel_animator** — `clip_*.mp4` per panel.  
9. **subtitle_generator** — SRT from timeline.  
10. **video_editor** — Concat clips, mux narration, optional **final BGM**, optional subtitle burn/embed, **`VIDEO_PLAYBACK_SPEED`**.  
11. **quality_checker** — Stream checks, duration / A-V delta gates.  
12. **Artifact cleanup** (default) — Deletes `clips/*.mp4`, `final/merged.mp4`, `final/concat.txt` when `RUN_KEEP_INTERMEDIATE_CLIPS=false` and the run succeeds.

---

## Source Types and Run Paths

Runs live under:

`outputs/runs/<run_key>/`

Webtoon URLs use nested keys:

`outputs/runs/<genre>/<title>/<episode>/`  
Example: `outputs/runs/romance/dirty-deeds/episode-1`

If the key exists, suffixes are applied (`episode-1_2`, …).

---

## Run Folder Structure

```text
outputs/runs/<run_key>/
  pages/          # PDF page images (PDF only)
  panels/         # Panel images
  audio/          # group_*.mp3, pause_*.mp3, narration.mp3, concat lists, etc.
  clips/          # clip_*.mp4 (removed after success if RUN_KEEP_INTERMEDIATE_CLIPS=false)
  final/
    video.mp4
    subtitles.srt # optional
    merged.mp4      # optional; removed after success when cleanup enabled
    concat.txt      # optional; removed after success when cleanup enabled
  meta/
    timeline.json
    audio_timeline.json
    job_report.json
```

**Panels and `audio/` are kept** so you can re-run or debug timing/TTS without re-OCRing. Enable `RUN_KEEP_INTERMEDIATE_CLIPS=true` to retain all per-panel clips and concat intermediates.

---

## Dialogue Model (`ScriptLine`)

Produced by **script_cleaner** (one line per OCR panel row, same order).

| Field | Notes |
|--------|--------|
| `panel_path` | Source panel image path |
| `narration` | Text for TTS; merged from LLM + OCR so words are not dropped |
| `speaker` | `male_1`, `male_2`, `female_1`, `female_2`, `narrator`, `unknown_1` |
| `gender` | `male`, `female`, `unknown` |
| `emotion` | `angry`, `sad`, `fear`, `happy`, `neutral` |
| `emotion_intensity` | Optional `0..1`; if omitted, **dialogue_analyzer** estimates from text |
| `voice`, `rendered_text`, `pause_sec`, `tts_provider` | Filled during audio pipeline |

**Script cleaner behavior**

- Strict enums for speaker / gender / emotion.  
- **Preserves** gasps and short vocals (`huu`, `haa`, etc.); very stretched tokens are normalized (e.g. long `uuu` → `uu`) for cleaner TTS.  
- **Merges** LLM output with OCR when the model under-generates, so OCR tokens are not lost.

---

## Audio Pipeline (ElevenLabs TTS only)

**External APIs**

- **OpenAI** — OCR + script cleaning (not TTS).  
- **ElevenLabs** — **Text-to-speech only** (`generate_tts` / streaming). There is **no** ElevenLabs Music API or Sound Generation client in this repo.

**Voice selection**

- `narrator` → `ELEVENLABS_VOICE_NARRATOR`  
- `gender` male/female → male/female defaults  
- `unknown` → alternates male/female by line index  
- Optional **`ELEVENLABS_VOICE_MAP_JSON`**: JSON object mapping `speaker` id → ElevenLabs voice id (overrides defaults for that speaker).

**Grouping**

- `AUDIO_GROUPING_ENABLED` — merge adjacent compatible lines into one TTS call (faster, fewer seams).  
- `AUDIO_STRICT_PER_LINE_TTS=true` — one TTS call per line (ignores grouping).  
- `AUDIO_GROUP_MAX_CHARS` — soft cap for merged text length.

**Performance text**

- **speech_renderer** adjusts punctuation/spacing from emotion + intensity (fear, sad, angry caps, etc.).  
- **pause_engine** adds pauses after lines; clips respect `MIN_PANEL_DURATION_SEC` / `MAX_PANEL_DURATION_SEC`.

**Narration music bed (local files only)**

Controlled by:

- `AUDIO_BED_IN_NARRATION` — master switch for mixing a bed **into** `narration.mp3`.  
- `AUDIO_MUSIC_LOCAL_MAP_JSON` — JSON `emotion` → absolute or cwd-relative path to a loopable track (dominant emotion across lines picks the file).  
- `AUDIO_USE_BGM_DEFAULT_AS_BED` — if no local-map hit, use `BGM_DEFAULT_PATH` as the bed **when** it exists.  
- `AUDIO_MUSIC_VOLUME` — bed level vs voice (voice-led `amix`, `duration=first`).

**Avoiding double BGM**

If the narration bed came from **`bgm_default`** (not from `AUDIO_MUSIC_LOCAL_MAP_JSON`) and the HTTP request did **not** set `bgm_path`, the **final video mux skips** `BGM_DEFAULT_PATH` so the same file is not mixed twice. If you pass `bgm_path` on the request, final mux still applies it.

**SFX and ambience**

- Local files under `assets/sfx/` via **sfx_engine** (`pick_sfx`).  
- Optional `AUDIO_AMBIENCE_PATH` loop mixed in **audio_mixer** after the voice (+bed) stem.

**Relevant env vars**

`ELEVENLABS_API_KEY`, `ELEVENLABS_API_BASE_URL`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_TTS_MODEL_FALLBACK`, `ELEVENLABS_OUTPUT_FORMAT`, `ELEVENLABS_VOICE_*`, `ELEVENLABS_VOICE_MAP_JSON`, `TTS_PROVIDER`, `TTS_PROVIDER_ORDER`, `AUDIO_*` and `BGM_*` as in `app/config.py`, `PROVIDER_TIMEOUT_SEC`, `PROVIDER_RETRIES`, `AUDIO_VOICE_FX_ENABLED`.

---

## Video Assembly

- Clips are concatenated (silent video), then merged with **`audio/narration.mp3`** (encoded to AAC in the final container).  
- **`VIDEO_PLAYBACK_SPEED`** (default `1.0`):  
  - `1.0` — no `setpts` / `atempo` speed change on narration; minimal processing.  
  - Other values — video `setpts` and narration `atempo` stay matched.  
- Optional **final BGM** track: `bgm_path` on the request, else `BGM_DEFAULT_PATH`, with `BGM_VOLUME` and `amix` `duration=first` against narration.

---

## Sync Strategy

1. Timeline uses measured audio segment durations.  
2. Empty narration panels get at least `MIN_PANEL_DURATION_SEC`.  
3. Final mux uses `-shortest` so video does not run past the primary audio bus.  
4. **quality_checker** reports `av_delta_sec` vs `AV_SYNC_MAX_DELTA_SEC`.

---

## Caching

Cache root: `outputs/cache/` (under pipeline `outputs/`).

Namespaces include:

- `ocr_engine`  
- `script_cleaner_chunks`, `script_cleaner`  
- `tts_audio` (when enabled in TTS layer)  

Disable: `ENABLE_CACHE=false`.

---

## API Endpoints

- `POST /generate` — main job.  
- Ops: `GET /ops`, `GET /ops/api/runs`, `GET /ops/api/runs/{run_path}`, `GET /ops/api/runs/{run_path}/video`, `POST /ops/api/generate`.  

`run_path` may be nested (URL-encoded slashes).

---

## Key Environment Variables (reference)

Aligned with `app/config.py` (see file for defaults):

**Core:** `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `OPENAI_MODEL`, `LOG_LEVEL`, `APP_ENV`

**Video / output:** `OUTPUT_ROOT`, `DEFAULT_FPS`, `TARGET_WIDTH`, `TARGET_HEIGHT`, `VIDEO_PLAYBACK_SPEED`, `RUN_KEEP_INTERMEDIATE_CLIPS`

**PDF / panels:** `MAX_PAGES`, `MAX_PAGE_MEGAPIXELS`, `DEFAULT_DPI`, `MIN_FREE_DISK_MB`

**Duration gates:** `MIN_PANEL_DURATION_SEC`, `MAX_PANEL_DURATION_SEC`, `MIN_VIDEO_DURATION_SEC`, `MAX_VIDEO_DURATION_SEC`

**OCR:** `OPENAI_OCR_BATCH_SIZE`, `OPENAI_OCR_MAX_IMAGE_DIM`, `OPENAI_OCR_JPEG_QUALITY`, `OPENAI_OCR_RECOVERY_BATCHES`

**Script cleaner:** `OPENAI_SCRIPT_BATCH_SIZE`, `OPENAI_SKIP_EMPTY_OCR_FOR_CLEANER`, `OPENAI_DEBUG_IO`

**Subtitles:** `ENABLE_SUBTITLES_DEFAULT`, `SUBTITLE_STRICT_FROM_SCRIPT`

**Audio / BGM:** `BGM_DEFAULT_PATH`, `BGM_VOLUME`, `AUDIO_BED_IN_NARRATION`, `AUDIO_MUSIC_LOCAL_MAP_JSON`, `AUDIO_MUSIC_VOLUME`, `AUDIO_USE_BGM_DEFAULT_AS_BED`, `AUDIO_AMBIENCE_PATH`, `AUDIO_AMBIENCE_VOLUME`, `AUDIO_SFX_VOLUME`, `AUDIO_VOICE_FX_ENABLED`, `AUDIO_GROUPING_ENABLED`, `AUDIO_STRICT_PER_LINE_TTS`, `AUDIO_GROUP_MAX_CHARS`, `ELEVENLABS_VOICE_MAP_JSON`, plus all `ELEVENLABS_*` TTS fields above

**Reliability:** `STAGE_TIMEOUT_SEC`, `PROVIDER_TIMEOUT_SEC`, `PROVIDER_RETRIES`, `AV_SYNC_MAX_DELTA_SEC`, `ENABLE_CACHE`

---

## Troubleshooting

### Input / network

- `PDF_NOT_FOUND`, Webtoon fetch errors → check path, URL, and network.

### OpenAI

- Rate limits / auth → `OPENAI_RATE_LIMITED`, `OPENAI_AUTH_FAILED`; reduce batch sizes, verify key.  
- `OPENAI_DEBUG_IO=true` logs request/response summaries for OCR/script stages.

### ElevenLabs TTS

- Empty script → `TTS_EMPTY_SCRIPT`.  
- Verify `ELEVENLABS_API_KEY` and voice IDs.

### Subtitles

- If FFmpeg has no `subtitles` filter, the pipeline falls back to a separate subtitle track.

### A/V drift

- Compare `ffprobe` on `video.mp4` streams vs `meta/timeline.json` / `audio/narration.mp3`.

### Unwanted narration wording

- Inspect cleaned script in `job_report.json` artifacts; clear `outputs/cache/script_cleaner*` (and full cache if needed) to invalidate.

### Missing music bed

- Ensure `AUDIO_BED_IN_NARRATION=true` and either a valid `AUDIO_MUSIC_LOCAL_MAP_JSON` entry for the dominant emotion or `BGM_DEFAULT_PATH` with `AUDIO_USE_BGM_DEFAULT_AS_BED=true`.

---

## Testing

```bash
cd manga_video_pipeline
python3 -m pytest tests/ -q
```

Smoke: short run with small `max_panels`, then inspect `meta/job_report.json` and play `final/video.mp4`.

---

## Security

- Do not commit real `.env` secrets.  
- Rotate keys if exposed.  
- Treat run folders as sensitive if they include copyrighted manga assets.
