from __future__ import annotations

from pathlib import Path

from pdf2image import convert_from_path

from app.config import settings
from app.models.schemas import PageAsset
from app.utils.errors import ValidationError


def load_pdf(pdf_path: str, pages_dir: Path) -> list[PageAsset]:
    source = Path(pdf_path)
    if not source.exists() or source.suffix.lower() != ".pdf":
        raise ValidationError(stage="pdf_loader", message=f"Invalid PDF path: {pdf_path}", error_code="INVALID_PDF")

    rendered = convert_from_path(str(source), dpi=settings.default_dpi)
    if not rendered:
        raise ValidationError(stage="pdf_loader", message="No pages extracted from PDF", error_code="EMPTY_PDF")
    if len(rendered) > settings.max_pages:
        raise ValidationError(
            stage="pdf_loader",
            message=f"PDF has {len(rendered)} pages, max allowed is {settings.max_pages}",
            error_code="MAX_PAGES_EXCEEDED",
        )

    assets: list[PageAsset] = []
    for i, img in enumerate(rendered, start=1):
        out_path = pages_dir / f"page_{i:03d}.png"
        img.save(out_path, "PNG")
        assets.append(PageAsset(page_index=i, image_path=str(out_path), width=img.width, height=img.height))
    return assets
