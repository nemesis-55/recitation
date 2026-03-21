from app.models.schemas import OcrResult
from app.services.script_cleaner import (
    _chunk_ocr,
    _extract_json_array,
    _final_ocr_safety_net,
    _merge_llm_and_ocr,
    _normalize_dialogue_text,
    _normalize_speaker_and_gender,
)


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


def test_extract_json_array_parses_plain_array():
    raw = '[{"text":"Hi","speaker":"male_1","gender":"male","emotion":"happy"}]'
    parsed = _extract_json_array(raw)
    assert parsed[0]["speaker"] == "male_1"


def test_normalize_dialogue_text_keeps_vocals_collapses_stretch():
    assert _normalize_dialogue_text("Huuu...") == "Huu..."
    assert _normalize_dialogue_text("Haaaa") == "Haa"
    assert _normalize_dialogue_text("I feel haaaappy") == "I feel happy"


def test_normalize_speaker_and_gender_infers_gender_from_speaker():
    speaker, gender = _normalize_speaker_and_gender("female_2", "unknown")
    assert speaker == "female_2"
    assert gender == "female"


def test_merge_llm_keeps_full_ocr_when_model_shortens():
    assert _merge_llm_and_ocr("hello there", "I said hello there friend") == _normalize_dialogue_text(
        "I said hello there friend"
    )


def test_merge_llm_keeps_expanded_model_when_ocr_subset():
    assert _merge_llm_and_ocr("Hello there my friend", "Hello friend") == _normalize_dialogue_text("Hello there my friend")


def test_merge_llm_preserves_full_ocr_when_llm_is_prefix():
    ocr = "Wait. Don't go."
    assert _merge_llm_and_ocr("Wait.", ocr) == _normalize_dialogue_text(ocr)


def test_final_ocr_safety_keeps_llm_when_all_ocr_tokens_present():
    ocr = "hello friend"
    nar = "hello you friend"
    assert _final_ocr_safety_net(ocr, nar) == _normalize_dialogue_text(nar)
