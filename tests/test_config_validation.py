import pytest

from app.config import settings
from app.services.preflight import run_preflight
from app.utils.errors import ValidationError


def test_preflight_requires_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr("app.services.preflight._validate_elevenlabs_auth", lambda: None)
    with pytest.raises(ValidationError) as exc:
        run_preflight("missing.pdf")
    assert exc.value.error_code == "MISSING_OPENAI_API_KEY"


def test_preflight_requires_elevenlabs_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "elevenlabs_api_key", None)
    monkeypatch.setattr("app.services.preflight._validate_elevenlabs_auth", lambda: None)
    with pytest.raises(ValidationError) as exc:
        run_preflight("missing.pdf")
    assert exc.value.error_code == "MISSING_ELEVENLABS_API_KEY"


def test_preflight_pdf_not_found_for_missing_local_file(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr("app.services.preflight._validate_elevenlabs_auth", lambda: None)
    with pytest.raises(ValidationError) as exc:
        run_preflight("/nonexistent/path/episode.pdf")
    assert exc.value.error_code == "PDF_NOT_FOUND"
