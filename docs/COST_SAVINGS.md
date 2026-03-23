# Cost reduction (OpenAI + ElevenLabs)

Use these **environment variables** in your repo-root or `manga_video_pipeline/.env`. No code changes required; restart the API after edits.

## Always on (high impact, low risk)

| Variable | Suggested | Why |
|----------|-----------|-----|
| `ENABLE_CACHE` | `true` | Reuses disk cache for OCR, TTS, ElevenLabs music/SFX/STS when keys match. **Keep this on.** |
| `OPENAI_EMOTION_REFINE_MAX_LINES` | `0` | Drops the **extra** OpenAI per-line emotion pass on early scene lines; dialogue still gets emotions from the main analyzer. Saves several chat calls per episode. |
| `ELEVENLABS_MUSIC_ENABLED` | `false` | Skips ElevenLabs **scene music** API. Use the **local BGM library** instead (see `BGM_LIBRARY_*` in README). Large savings if you were generating music every scene. |
| `BGM_LIBRARY_PREFER_LOCAL` | `true` | Uses persisted `outputs/cache/bgm_library/…` slots before per-scene ElevenLabs music. Selection maps **emotion → mood family** (10 styles); larger `BGM_LIBRARY_COUNT` adds **variants** (`bgm_10`… same family as `bgm_00`), not random unrelated tracks. |
| `ELEVENLABS_SFX_ENABLED` | `false` | Skips ElevenLabs SFX (if you don’t need them). |

## OpenAI vision / OCR (smaller payloads = lower image cost)

| Variable | Aggressive (cheaper) | Balanced (default-ish) |
|----------|----------------------|---------------------------|
| `OPENAI_OCR_MAX_IMAGE_DIM` | `512`–`640` | `768` |
| `OPENAI_OCR_JPEG_QUALITY` | `50`–`65` | `72` |

If OCR quality drops, raise dim/quality slightly. Cached panels skip repeat API calls.

## OpenAI dialogue (fewer requests)

| Variable | Suggested |
|----------|-----------|
| `OPENAI_DIALOGUE_BATCH_SIZE` | `8`–`12` if context allows (fewer batches, larger payloads—watch token limits). |
| `OPENAI_EMOTION_REFINE_MAX_LINES` | `0` (see above). |

Using a **cheaper** chat model for dialogue-only is possible via `OPENAI_DIALOGUE_ANALYSIS_MODEL` (e.g. mini) while keeping a stronger model for OCR if you split that in the future—today’s pipeline shares `OPENAI_MODEL` for OCR; tune globally only if acceptable.

## ElevenLabs: TTS and music

| Variable | Suggested |
|----------|-----------|
| `ELEVENLABS_TTS_MODEL` | `eleven_flash_v2_5` (default) — cheaper/faster than heavier models. |
| `ELEVENLABS_OUTPUT_FORMAT` | `mp3_44100_128` or lower bitrate if your plan bills by output size. |
| `ELEVENLABS_TTS_LINE_CONTEXT` | `false` | **More cache hits** for identical lines (less prosody context). Tradeoff: slightly less natural phrasing. |
| `AUDIO_GROUPING_ENABLED` + `AUDIO_GROUP_MAX_CHARS` | Keep grouping **on**; slightly higher `AUDIO_GROUP_MAX_CHARS` can **reduce TTS calls** (fewer clips). |

## What not to disable for “cost” without a plan

- `OPENAI_DIALOGUE_ANALYSIS_ENABLED` — saves a lot, but hurts narration quality (heuristic-only mode).
- `AUDIO_BED_IN_NARRATION` — turning off removes under-bed music entirely unless you add it only at mux time.

## Quick “budget” profile (copy into `.env`)

```env
ENABLE_CACHE=true
OPENAI_EMOTION_REFINE_MAX_LINES=0
ELEVENLABS_MUSIC_ENABLED=false
BGM_LIBRARY_PREFER_LOCAL=true
ELEVENLABS_SFX_ENABLED=false
# Optional: tighter OCR payload (validate on your titles)
# OPENAI_OCR_MAX_IMAGE_DIM=640
# OPENAI_OCR_JPEG_QUALITY=65
# Optional: more TTS cache hits
# ELEVENLABS_TTS_LINE_CONTEXT=false
```

Ensure `BGM_DEFAULT_PATH` points at a loopable MP3 if you rely on library fallback when slots are empty.
