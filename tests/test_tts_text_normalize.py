from app.services.audio.tts_text_normalize import normalize_tts_narration


def test_normalize_collapses_stretched_letters_to_double():
    # Pronounceable stretch: many o's → "oo" ("woo") — OCR spellings like "hui" stay.
    assert normalize_tts_narration("hui.wooooooooo") == "hui.woo"
    assert normalize_tts_narration("yesss") == "yess"
    assert normalize_tts_narration("soooo") == "soo"


def test_normalize_preserves_double_letters():
    assert normalize_tts_narration("bookkeeper") == "bookkeeper"


def test_normalize_does_not_respell_words():
    assert normalize_tts_narration("Hui said") == "Hui said"
    assert normalize_tts_narration("HUI!") == "HUI!"


def test_normalize_trims_excess_punctuation():
    assert normalize_tts_narration("wait!!!") == "wait!"


def test_render_speech_tts_applies_stretch_only(monkeypatch):
    from app.config import settings as app_settings
    from app.services.audio.speech_renderer import render_speech

    monkeypatch.setattr(app_settings, "tts_narration_normalize_enabled", True)
    out = render_speech("hui.wooooooooo", "neutral", 0.4)
    assert "hui" in out.lower()
    assert "woo" in out.lower()
    assert "woooooooo" not in out.lower()


def test_render_speech_display_keeps_ocr_stretch(monkeypatch):
    from app.config import settings as app_settings
    from app.services.audio.speech_renderer import render_speech_for_display

    monkeypatch.setattr(app_settings, "tts_narration_normalize_enabled", True)
    out = render_speech_for_display("hui.wooooooooo", "neutral", 0.4)
    assert "woooooooo" in out.replace(" ", "").lower() or "woooooooo" in out.lower()


def test_render_speech_can_disable_normalization(monkeypatch):
    from app.config import settings as app_settings
    from app.services.audio.speech_renderer import render_speech

    monkeypatch.setattr(app_settings, "tts_narration_normalize_enabled", False)
    out = render_speech("hui.wooooooooo", "neutral", 0.4)
    assert "woooooooo" in out.lower()
