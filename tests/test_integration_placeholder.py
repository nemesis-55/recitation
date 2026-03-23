"""Placeholder for full E2E runs (not part of default CI)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PDF = _ROOT / "tests" / "fixtures" / "sample_manga.pdf"


@pytest.mark.skip(reason="Requires real API keys, ffmpeg, poppler, and tests/fixtures/sample_manga.pdf.")
def test_end_to_end_pipeline_fixture_exists():
    assert _FIXTURE_PDF.exists(), f"Add fixture PDF at {_FIXTURE_PDF}"
