# Manga Video Pipeline — Detailed Documentation

## Overview

The runtime is now **SRT-driven**. Subtitles are the source of truth for timing and dialogue text.

Inputs:
- `pdf_path` (or webtoon URL)
- optional `srt_path` (if missing, timeline is auto-generated from OCR)

Outputs:
- `final/video.mp4`
- `audio/narration.mp3`
- `meta/timeline.json`, `meta/audio_timeline.json`, `meta/job_report.json`

## Runtime Flow

1. `preflight`
2. `pdf_loader` / `webtoon_loader`
3. `panel_extractor` (PDF only)
4. `srt_loader` (`load_srt_timeline`)
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
- Final limiter avoids clipping.

## Provider Policy

- No local fallback for ElevenLabs generation.
- SFX/Music/TTS failures raise provider errors and stop run.

## Important Settings

- SRT: `SRT_REQUIRE_INPUT`, `SRT_MIN_LINE_DURATION_SEC`, `SRT_MAX_LINE_DURATION_SEC`
- OpenAI analysis: `OPENAI_DIALOGUE_ANALYSIS_ENABLED`, `OPENAI_DIALOGUE_ANALYSIS_MODEL`
- ElevenLabs TTS: `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_OUTPUT_FORMAT`, `ELEVENLABS_VOICE_*`
- ElevenLabs SFX: `ELEVENLABS_SFX_ENABLED`, `ELEVENLABS_SFX_MODEL_ID`, `ELEVENLABS_SFX_PROMPT_INFLUENCE`
- ElevenLabs Music: `ELEVENLABS_MUSIC_ENABLED`, `ELEVENLABS_MUSIC_MODEL_ID`, `ELEVENLABS_MUSIC_FORCE_INSTRUMENTAL`
- Mixer: `AUDIO_MIXER_*` (voice/sfx/music gain + ducking + normalize)
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
- SRT source selection (`provided` vs `auto_generated_from_ocr`)
- dialogue analyzer chunk progress
- OCR pacing intervals and batch progress
- audio pipeline milestones (line generation and mixer begin/end)

## Testing

```bash
cd manga_video_pipeline
python3 -m pytest tests/ -q
```
