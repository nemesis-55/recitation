from app.models.schemas import OcrResult
from app.services.script_cleaner import _chunk_ocr, _extract_json_array


def test_chunk_ocr_batches():
    items = [
        OcrResult(panel_path=f"{i}.jpg", text=f"t{i}", confidence=0.8, low_confidence=False)
        for i in range(7)
    ]
    chunks = _chunk_ocr(items, 3)
    assert [len(c) for c in chunks] == [3, 3, 1]


def test_extract_json_array_from_markdown_fence():
    raw = """```json
[
  {"panel_path":"p1","narration":"line 1","emotion":"neutral"}
]
```"""
    parsed = _extract_json_array(raw)
    assert isinstance(parsed, list)
    assert parsed[0]["panel_path"] == "p1"
