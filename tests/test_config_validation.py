import pytest

from app.services.preflight import run_preflight
from app.utils.errors import ValidationError


def test_preflight_requires_provider_keys():
    with pytest.raises(ValidationError) as exc:
        run_preflight("missing.pdf")
    assert exc.value.error_code in {"MISSING_OPENAI_API_KEY", "MISSING_RUNWAY_API_KEY", "PDF_NOT_FOUND"}
