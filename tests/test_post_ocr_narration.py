from app.models.schemas import SrtTimelineLine
from app.services.audio.post_ocr_narration import filter_ocr_narration_and_extract_sfx


def test_filter_ocr_narration_extracts_sfx_and_keeps_dialogue():
    lines = [
        SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="WHOOSH\nSLAM"),
        SrtTimelineLine(index=2, start_sec=2.0, end_sec=4.0, text="Get down now!\nSLASH"),
    ]
    out = filter_ocr_narration_and_extract_sfx(lines)
    assert out[0].text == ""
    assert out[0].sfx_cues == ["movement", "impact"]
    assert "Get down now!" in out[1].text
    assert "movement" in out[1].sfx_cues


def test_filter_ocr_narration_ignores_low_confidence_breath_noise():
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="HUFF\nHUMM\nPANT")]
    out = filter_ocr_narration_and_extract_sfx(lines)
    assert out[0].sfx_cues == []


def test_filter_ocr_narration_extracts_clomp_and_cough_as_sfx():
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="CLOMP\nCLOMP\nCOUGH")]
    out = filter_ocr_narration_and_extract_sfx(lines)
    assert out[0].text == ""
    assert out[0].sfx_cues == ["thump", "cough"]


def test_filter_ocr_narration_strips_embedded_sfx_tokens_from_spoken_text():
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="CLOMP Hey, move now! COUGH")]
    out = filter_ocr_narration_and_extract_sfx(lines)
    assert out[0].text == "Hey, move now!"
    assert out[0].sfx_cues == ["thump", "cough"]


def test_filter_ocr_narration_can_disable_sfx_cues_but_keep_cleanup():
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="CLOMP Hey, move now! COUGH")]
    out = filter_ocr_narration_and_extract_sfx(lines, emit_sfx_cues=False)
    assert out[0].text == "Hey, move now!"
    assert out[0].sfx_cues == []

