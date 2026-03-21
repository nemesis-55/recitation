from __future__ import annotations

import shutil
from pathlib import Path

import requests

from app.config import settings
from app.models.schemas import PageAsset
from app.services.webtoon_loader import is_webtoon_url
from app.utils.errors import ValidationError


def _validate_elevenlabs_auth() -> None:
    headers = {"xi-api-key": str(settings.elevenlabs_api_key)}
    try:
        # ElevenLabs developer APIs accept xi-api-key header.
        resp = requests.get("https://api.elevenlabs.io/v1/user", headers=headers, timeout=min(settings.provider_timeout_sec, 10))
        if resp.status_code == 401:
            raise ValidationError(
                "preflight",
                "ELEVENLABS_API_KEY is unauthorized (401). Use a valid key from ElevenLabs developers dashboard.",
                "INVALID_ELEVENLABS_API_KEY",
            )
        resp.raise_for_status()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("preflight", f"ElevenLabs auth check failed: {exc}", "ELEVENLABS_AUTH_CHECK_FAILED") from exc


def run_preflight(source_path: str) -> None:
    if not settings.openai_api_key:
        raise ValidationError("preflight", "OPENAI_API_KEY is missing", "MISSING_OPENAI_API_KEY")
    tts_provider = (settings.tts_provider or "elevenlabs").lower()
    if tts_provider != "elevenlabs":
        raise ValidationError("preflight", f"Unsupported TTS_PROVIDER: {settings.tts_provider}", "INVALID_TTS_PROVIDER")
    if not settings.elevenlabs_api_key:
        raise ValidationError("preflight", "ELEVENLABS_API_KEY is missing", "MISSING_ELEVENLABS_API_KEY")
    _validate_elevenlabs_auth()
    if not is_webtoon_url(source_path):
        source = Path(source_path)
        if not source.exists():
            raise ValidationError("preflight", f"PDF does not exist: {source_path}", "PDF_NOT_FOUND")
    usage = shutil.disk_usage(settings.output_root.parent if settings.output_root.parent.exists() else Path("."))
    free_mb = usage.free / (1024 * 1024)
    if free_mb < settings.min_free_disk_mb:
        raise ValidationError("preflight", f"Insufficient disk: {free_mb:.1f} MB free", "LOW_DISK_SPACE")


def validate_page_resolution(pages: list[PageAsset]) -> None:
    for page in pages:
        mp = (page.width * page.height) / 1_000_000
        if mp > settings.max_page_megapixels:
            raise ValidationError(
                "pdf_loader",
                f"Page {page.page_index} too large ({mp:.2f} MP > {settings.max_page_megapixels} MP)",
                "PAGE_RESOLUTION_TOO_HIGH",
            )
