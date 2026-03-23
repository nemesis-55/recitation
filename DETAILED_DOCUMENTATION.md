# Manga Video Pipeline — Detailed Documentation

## Overview

The runtime is **SRT-first with OCR fallback**. Dialogue timing uses provided SRT when available, otherwise OCR-derived timeline.

Inputs:
- `pdf_path` (or webtoon URL)
- optional `srt_path`

Outputs:
- `final/video.mp4`
- `audio/narration.mp3`
- `meta/timeline.json`, `meta/audio_timeline.json`, `meta/job_report.json`

## Runtime Flow

1. `preflight`
2. `pdf_loader` / `webtoon_loader`
3. `panel_extractor` (PDF only)
4. `srt_loader` (uses provided SRT or auto-generates timeline from OCR)
5. `narrator`:
   - `dialogue_analyzer.analyze_srt_timeline` (OpenAI)
   - `speech_renderer.render_speech` (deterministic)
   - `tts_elevenlabs.generate_tts` per SRT line
   - optional STS modulation (`elevenlabs_sts`)
   - `sfx_engine.materialize_sfx_for_line` (ElevenLabs Sound Effects)
   - `music_engine.resolve_music_bed` (ElevenLabs Music)
   - `audio_mixer.mix_audio` (ducking + limiter/normalization)
6. `timeline_builder` (`build_timeline_from_srt`)
7. `panel_animator`
8. `subtitle_generator`
9. `video_editor`
10. `quality_checker`

**Panel video:** `panel_animator` builds **two** clip streams — **YouTube** (16:9 1920×1080: **full webtoon panel** centered in a safe rectangle ~`PANEL_SCREEN_FILL_RATIO` of the frame, letterboxing as needed; optional **Ken Burns (YouTube)**: start zoomed on **center** at `PANEL_YOUTUBE_KEN_BURNS_ZOOM`, then **ease out to full panel** over the clip (zoom-out lasts the full panel duration — scales with audio/screen time) + X/Y pan via `PANEL_YOUTUBE_ZOOM_MOTION`, `PANEL_YOUTUBE_MOTION_AMP_SCALE`; **Reel** still uses symmetric zoom in/out + pan via `PANEL_*_KEN_BURNS_ZOOM` (9:16 1080×1920 **cover crop**: art fills the phone screen; same zoom in/out + pan via `PANEL_REEL_ZOOM_MOTION`, `PANEL_REEL_KEN_BURNS_ZOOM`, `PANEL_REEL_MOTION_AMP_SCALE`; set `PANEL_REEL_FULL_BLEED=false` for legacy letterboxed fit). Fades soften panel boundaries (`PANEL_TRANSITION_FADE_SEC`). Outputs: `final/video_youtube.mp4`, `final/video_reel.mp4`, and `final/reels/chunks/reel_chunk_*.mp4`.

**Sample clips (preview motion without a full run):** from the `manga_video_pipeline/` directory:

```bash
python scripts/render_ken_burns_sample.py
# optional: custom panel + length
python scripts/render_ken_burns_sample.py --panel /path/to/panel.jpg --duration 2.5
```

Writes `outputs/samples/sample_youtube_ken_burns.mp4` and `outputs/samples/sample_reel_ken_burns.mp4` (uses your `.env` `PANEL_*` settings).

When `WEBTOON_CATALOG_ENABLED=true`, startup includes a blocking catalog refresh stage before the API begins serving traffic.

## Key Contracts

- `SrtTimelineLine`: `index`, `start_sec`, `end_sec`, `text`, `speaker`, `emotion`, `intensity`.
- `GenerateResponse` success includes:
  - `video_path`
  - `audio_path`
  - `quality` (`cinematic`)
- `EpisodeRangeGenerateRequest` and `EpisodeRangeGenerateResponse` drive sequential episode-range runs from local catalog.

## Local Webtoon Catalog

Catalog file is stored under `outputs/meta/<WEBTOON_CATALOG_FILE>`.

Supported operations:
- crawl/refresh catalog
- search by `query` and `genre`
- list episodes by `title_slug`

Ops endpoints:
- `GET /ops/api/manga`
- `GET /ops/api/manga/{title_slug}/episodes`
- `GET /ops/api/manga/status`
- `POST /ops/api/manga/refresh`
- `POST /ops/api/generate-range`

Episode range runs are processed sequentially and return per-episode results.

## Audio Design

- Voice is primary.
- Music is scene-level and mixed under voice.
- SFX are event-driven (`hit`, `fall`, `fear`, `movement` mapping).
- Mixer applies sidechain ducking (music attenuates while voice is present).
- **Music bed only** (not voice): optional high-pass + gentle `dynaudnorm` so beds sit under narration without changing line timings or mix duration (`AUDIO_MIXER_MUSIC_HIGHPASS_HZ`, `AUDIO_MIXER_MUSIC_DYNAUDNORM_ENABLED`).
- **Multi-scene episodes**: optional **crossfade** when stitching scene narration MP3s (`AUDIO_SCENE_CROSSFADE_SEC`); flattened timeline offsets subtract overlap so subtitle sync stays correct.
- Final limiter avoids clipping.

## Provider Policy

- No local fallback for ElevenLabs generation.
- SFX/Music/TTS failures raise provider errors and stop run.

## Important Settings

- SRT: `SRT_REQUIRE_INPUT`, `SRT_MIN_LINE_DURATION_SEC`, `SRT_MAX_LINE_DURATION_SEC`
- OpenAI analysis: `OPENAI_DIALOGUE_ANALYSIS_ENABLED`, `OPENAI_DIALOGUE_ANALYSIS_MODEL`
- ElevenLabs TTS: `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_OUTPUT_FORMAT`, `ELEVENLABS_VOICE_*`, `ELEVENLABS_TTS_SPEECH_SPEED`, **gender-unified tempo** `ELEVENLABS_TTS_SPEED_MALE`, `ELEVENLABS_TTS_SPEED_FEMALE`, `ELEVENLABS_TTS_SPEED_UNKNOWN`, `ELEVENLABS_TTS_SPEED_NARRATOR`, and `ELEVENLABS_TTS_EMOTION_SPEED_MIX` (how much emotion nudges speed vs. flat per-gender base)
- ElevenLabs SFX: `ELEVENLABS_SFX_ENABLED`, `ELEVENLABS_SFX_MODEL_ID`, `ELEVENLABS_SFX_PROMPT_INFLUENCE`
- ElevenLabs Music: `ELEVENLABS_MUSIC_ENABLED`, `ELEVENLABS_MUSIC_MODEL_ID`, `ELEVENLABS_MUSIC_FORCE_INSTRUMENTAL`
- Mixer: `AUDIO_MIXER_*` (voice/sfx/music gain + ducking + master normalize; music bed: `AUDIO_MIXER_MUSIC_HIGHPASS_HZ`, `AUDIO_MIXER_MUSIC_DYNAUDNORM_ENABLED`). If the scene bed is already in `narration.mp3`, mux does not add `BGM_DEFAULT_PATH` again — set `BGM_DEFAULT_PATH` when `narration_music_source` is `none` and you still want a bed at mux.
- Panels / video: `PANEL_TRANSITION_FADE_SEC`, `PANEL_YOUTUBE_ZOOM_MOTION`, `PANEL_YOUTUBE_KEN_BURNS_ZOOM` (zoom-in level, ~1.09), `PANEL_YOUTUBE_MOTION_AMP_SCALE`, **YouTube blurred backdrop** `PANEL_YOUTUBE_BLUR_BACKGROUND_ENABLED`, `PANEL_YOUTUBE_BLUR_BACKGROUND_SIGMA`, optional `PANEL_YOUTUBE_BLUR_BACKGROUND_BRIGHTNESS`, **per-panel motion rotation** `PANEL_YOUTUBE_MOTION_ROTATION` (comma list: `center_zoom_out`, `ken_burns`, `static`, `slow_drift`), `PANEL_REEL_FULL_BLEED` (cover-crop 9:16 full-screen), `PANEL_REEL_ZOOM_MOTION`, `PANEL_REEL_KEN_BURNS_ZOOM`, `PANEL_REEL_MOTION_AMP_SCALE`, `PANEL_SCREEN_FILL_RATIO` (e.g. `0.92` ≈ 8% margin)
- Ops catalog: episode checkboxes load from **`load_catalog()`** / `WEBTOON_CATALOG_FILE` (same JSON written by the Webtoon crawler); `/ops/api/manga/{slug}/episodes` returns `source: webtoon_catalog_cache` and `catalog_path`. Pipeline Ops also supports **episode min/max**: checkboxes via “Select range in list”, or **Generate episode range** (`episode_from` / `episode_to` on `POST /ops/api/generate-range`).
- Webtoon catalog crawler: `WEBTOON_CATALOG_MAX_EPISODES_PER_TITLE` (cap per series), **`WEBTOON_CATALOG_MAX_LIST_PAGES`** (follows `page=` on list URLs to collect more episodes), `WEBTOON_CATALOG_MAX_TITLES_PER_GENRE`, `WEBTOON_CATALOG_WORKERS`.
- TTS: `TTS_NARRATION_NORMALIZE_ENABLED` — **TTS only** (subtitles keep OCR): collapse stretched Latin letters to a readable double (e.g. `woooooooo`→`woo`); OCR wording is not respelled. Display / `performance_text` uses `render_speech_for_display`; ElevenLabs gets `render_speech` with pronunciation fixes.
- Optional STS: `ELEVENLABS_STS_*`
- Catalog: `WEBTOON_CATALOG_*`
- OpenAI pacing/batching: `OPENAI_OCR_BATCH_SIZE`, `OPENAI_OCR_BATCH_PACE_SEC`, `OPENAI_DIALOGUE_BATCH_SIZE`, `OPENAI_DIALOGUE_BATCH_PACE_SEC`

## Caching

Byte caches are used for:
- `tts_audio`
- `elevenlabs_sfx`
- `elevenlabs_music`
- `elevenlabs_sts` (when enabled)

## INFO Observability Logs

INFO logs are emitted for:
- startup blocking catalog refresh begin/end + duration
- crawler progress (genre/title/episode counts and failures)
- sequential episode queue lifecycle
- OCR timeline generation status
- dialogue analyzer chunk progress
- OCR pacing intervals and batch progress
- audio pipeline milestones (line generation and mixer begin/end)

## Testing

```bash
cd manga_video_pipeline
python3 -m pytest tests/ -q
```
