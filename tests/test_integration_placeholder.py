from pathlib import Path

import pytest


@pytest.mark.skip(reason="Requires real API keys, ffmpeg, poppler, and a fixture PDF.")
def test_end_to_end_pipeline_fixture_exists():
    fixture_pdf = Path("manga_video_pipeline/tests/fixtures/sample_manga.pdf")
    assert fixture_pdf.exists()
