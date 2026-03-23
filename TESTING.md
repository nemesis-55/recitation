# Testing (`manga_video_pipeline`)

## Quick run

From this directory (`manga_video_pipeline/`):

```bash
python3 -m pytest
```

Or a subset:

```bash
python3 -m pytest tests/test_dialogue_analyzer.py tests/test_video_editor.py -q
```

## Layout

| Path | Role |
|------|------|
| `tests/` | Unit and integration-style tests (mocked providers) |
| `tests/conftest.py` | Adds package root to `sys.path` for imports |
| `pytest.ini` | `testpaths`, `pythonpath`, warning filters |

## What is covered

- Config & cache utilities, OCR/dialogue/scene analyzers (mocked OpenAI)
- Audio: mixer, pipeline, scene processor, narrator, cinematic rules
- Video editor, timeline, subtitles, webtoon loader
- Ops routes, catalog/queue, episode queue (when enabled)

## What is not in CI by default

- **Skipped** `tests/test_integration_placeholder.py` — full PDF→video run needs real keys, ffmpeg, and fixtures.

## Environment

Tests should pass **without** API keys (mocks / disabled paths). For local runs, a `.env` at repo root or `manga_video_pipeline/.env` is optional.

## Optional debug logging

Set `PIPELINE_DEBUG_NDJSON_PATH` to a file path to append NDJSON lines from the audio pipeline/mixer when diagnostics are needed. Leave unset for normal runs.
