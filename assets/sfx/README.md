# Sound effects assets (`assets/sfx/`)

The pipeline can mix **short, subtle** one-shots under narration via `pick_sfx()` in `app/services/audio/sfx_engine.py`. Files are **optional**: missing files are skipped without failing the job.

## Files used by current code

| File | When it is picked |
|------|-------------------|
| `breath_light.mp3` | Line emotion is `fear` |
| `impact_thump_soft.mp3` | Line emotion is `angry` |
| `soft_exhale.mp3` | Line emotion is `sad` |
| `room_tone_soft.mp3` | Line emotion is `neutral` or `happy` |
| `breath_heavy.mp3` | Extra layer when narration matches exertion patterns (`hu`, `ha`, `ah`, `uh`, …) |

At most **two** SFX paths are returned per line (emotion file + optional breath heavy).

Other filenames may exist in this folder for your own experiments; they are **not** wired unless you extend `sfx_engine.py`.

## Loudness

- Leave **headroom** (~−6 to −12 dBFS peak) so `AUDIO_SFX_VOLUME` (default `0.16`) stays subtle.
- One-shots: **~0.3–2.0 s** works well.

## Sourcing

Use **royalty-free** packs or original recordings. This repo does **not** call ElevenLabs Sound Generation; everything here is **local files only**.

## Related env vars

- `AUDIO_SFX_VOLUME` — per-event level in **audio_mixer**  
- `AUDIO_AMBIENCE_PATH` / `AUDIO_AMBIENCE_VOLUME` — optional loop under the full narration stem  
- `AUDIO_MUSIC_VOLUME`, `AUDIO_MUSIC_LOCAL_MAP_JSON`, `AUDIO_BED_IN_NARRATION`, `BGM_DEFAULT_PATH` — instrumental **bed** mixed into `narration.mp3` (see main docs)

Full pipeline audio behavior: [`DETAILED_DOCUMENTATION.md`](../../DETAILED_DOCUMENTATION.md).
