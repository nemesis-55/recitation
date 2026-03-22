from app.models.schemas import SrtTimelineLine
from app.services.audio.dialogue_analyzer import _enforce_speaker_consistency, _normalize_chunk_rows


def test_normalize_chunk_rows_truncates_oversized_response():
    rows = [{"speaker": "narrator"} for _ in range(6)]
    normalized = _normalize_chunk_rows(rows, expected_len=1)
    assert len(normalized) == 1
    assert normalized[0]["speaker"] == "narrator"


def test_normalize_chunk_rows_pads_undersized_response():
    rows = [{"speaker": "male_1"}]
    normalized = _normalize_chunk_rows(rows, expected_len=3)
    assert len(normalized) == 3
    assert normalized[0]["speaker"] == "male_1"
    assert normalized[1] == {}
    assert normalized[2] == {}


def test_enforce_speaker_consistency_flips_same_gender_on_turn_markers():
    lines = [
        SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="- Get ready."),
        SrtTimelineLine(index=2, start_sec=1.0, end_sec=2.0, text="- I am ready."),
        SrtTimelineLine(index=3, start_sec=2.0, end_sec=3.0, text="- Move now."),
    ]
    rows = [
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
        {"speaker": "male_1", "emotion": "neutral", "intensity": 0.4},
    ]
    fixed = _enforce_speaker_consistency(rows, lines)
    assert fixed[0]["speaker"] == "male_1"
    assert fixed[1]["speaker"] == "male_2"
