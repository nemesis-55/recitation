import json

from app.models.schemas import SrtTimelineLine
from app.services.audio import narration_polish as np


def test_polish_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(np.settings, "openai_narration_polish_enabled", False)
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Hello world")]
    out = np.polish_srt_lines(lines)
    assert out[0].text == "Hello world"


def test_polish_skipped_without_api_key(monkeypatch):
    monkeypatch.setattr(np.settings, "openai_narration_polish_enabled", True)
    monkeypatch.setattr(np.settings, "openai_api_key", None)
    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="Hello")]
    assert np.polish_srt_lines(lines)[0].text == "Hello"


def test_polish_calls_openai_and_updates_text(monkeypatch):
    monkeypatch.setattr(np.settings, "openai_narration_polish_enabled", True)
    monkeypatch.setattr(np.settings, "openai_api_key", "k")
    monkeypatch.setattr(np.settings, "use_mock_llm", False)
    monkeypatch.setattr(np.settings, "openai_narration_polish_batch_size", 4)
    monkeypatch.setattr(np.settings, "narration_polish_max_words", 22)
    monkeypatch.setattr(np.settings, "provider_retries", 0)
    monkeypatch.setattr(np.settings, "enable_cache", False)

    class _Resp:
        output_text = json.dumps(
            {
                "polished": [
                    {"index": 1, "text": "A pale mass waited in the alley."},
                ]
            }
        )

    monkeypatch.setattr(
        "app.services.audio.narration_polish._responses_create_deterministic",
        lambda _client, _model, _prompt: _Resp(),
    )

    lines = [SrtTimelineLine(index=1, start_sec=0.0, end_sec=2.0, text="#gross\nSomething weird.")]
    out = np.polish_srt_lines(lines)
    assert out[0].text == "A pale mass waited in the alley."
