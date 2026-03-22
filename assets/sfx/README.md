# Sound effects assets (`assets/sfx/`)

The cinematic runtime now uses **ElevenLabs Sound Effects API** for SFX generation.

- Event mapping: `hit`, `fall`, `fear`, `movement`
- Source: generated via `/v1/sound-generation`
- Fallback policy: none (provider failure is fatal)

This folder can still hold manual reference assets for development, but runtime SFX generation does not depend on fixed local filenames.

## Loudness

- Leave **headroom** (~−6 to −12 dBFS peak) so `AUDIO_SFX_VOLUME` (default `0.16`) stays subtle.
- One-shots: **~0.3–2.0 s** works well.

## Sourcing

Use **royalty-free** packs or original recordings for local experimentation.

## Related env vars

- `ELEVENLABS_SFX_ENABLED`
- `ELEVENLABS_SFX_MODEL_ID`
- `ELEVENLABS_SFX_PROMPT_INFLUENCE`
- `AUDIO_MIXER_SFX_GAIN`

Full pipeline audio behavior: [`DETAILED_DOCUMENTATION.md`](../../DETAILED_DOCUMENTATION.md).
