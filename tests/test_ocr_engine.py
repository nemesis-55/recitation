from pathlib import Path

from app.models.schemas import PanelAsset
from app.services.ocr_engine import (
    _chunk_panels,
    _encode_image_data_url,
    _extract_json_array,
    _extract_output_text,
    _normalize_batch_items,
    _parse_retry_after_seconds,
)


class DummyResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class DummyError(Exception):
    pass


def test_extract_output_text():
    resp = DummyResponse(" hello world \n")
    assert _extract_output_text(resp) == "hello world"


def test_encode_image_data_url(tmp_path: Path):
    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    out = _encode_image_data_url(str(img))
    assert out.startswith("data:image/jpeg;base64,")


def test_chunk_panels():
    panels = [
        PanelAsset(page_index=1, panel_index=i, image_path=f"{i}.jpg", bbox=(0, 0, 10, 10))
        for i in range(1, 8)
    ]
    chunks = _chunk_panels(panels, 3)
    assert [len(c) for c in chunks] == [3, 3, 1]


def test_extract_json_array_from_markdown_fence():
    raw = """```json
[
  {"text":"a","confidence":0.9},
  {"text":"b","confidence":0.2}
]
```"""
    parsed = _extract_json_array(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_extract_json_array_from_logged_response_shape():
    raw = """```json
[
    {
        "text": "WARNING\\n\\nTHE FOLLOWING EPISODE\\nCONTAINS DEPICTIONS OF\\nSEXUAL HARASSMENT THAT MAY BE\\nUPSETTING FOR SOME READERS.\\nVIEWER DISCRETION IS ADVISED.",
        "confidence": 1.0
    },
    {
        "text": "IT FELT SO UNFAIR.",
        "confidence": 1.0
    },
    {
        "text": "ONE FLEETING MOMENT,\\nand MISFORTUNE SWALLOWED\\nME WHOLE.",
        "confidence": 1.0
    }
]
```"""
    parsed = _extract_json_array(raw)
    assert len(parsed) == 3
    assert parsed[0]["confidence"] == 1.0


def test_normalize_batch_items_truncates_and_pads():
    data = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    assert len(_normalize_batch_items(data, 2)) == 2
    padded = _normalize_batch_items([{"text": "a"}], 3)
    assert len(padded) == 3
    assert padded[2]["text"] == ""


def test_parse_retry_after_seconds_from_error_message_ms():
    exc = DummyError("Rate limit reached. Please try again in 688ms.")
    parsed = _parse_retry_after_seconds(exc)
    assert parsed is not None
    assert 0.6 <= parsed <= 0.8


def test_parse_retry_after_seconds_from_error_message_seconds():
    exc = DummyError("Rate limit reached. Please try again in 1.377s.")
    parsed = _parse_retry_after_seconds(exc)
    assert parsed is not None
    assert 1.2 <= parsed <= 1.5
