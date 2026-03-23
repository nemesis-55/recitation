from pathlib import Path

from app.config import settings as app_settings
from app.services.audio import sfx_engine as se
from app.services.audio.sfx_engine import generate_sfx_to_file


def test_generate_sfx_to_file_uses_runtime_cache(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_settings, "elevenlabs_sfx_enabled", True)
    monkeypatch.setattr(app_settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr(app_settings, "provider_retries", 0)

    cache_store: dict[str, bytes] = {}
    calls = {"count": 0}

    monkeypatch.setattr(se, "read_cache_bytes", lambda _ns, key: cache_store.get(key))
    monkeypatch.setattr(se, "write_cache_bytes", lambda _ns, key, payload: cache_store.__setitem__(key, payload))

    class _Resp:
        status_code = 200
        content = b"sfx-bytes"

        @staticmethod
        def raise_for_status():
            return None

    def _fake_post(*_args, **_kwargs):
        calls["count"] += 1
        return _Resp()

    monkeypatch.setattr(se.requests, "post", _fake_post)

    out1 = tmp_path / "sfx1.mp3"
    out2 = tmp_path / "sfx2.mp3"
    generate_sfx_to_file("impact cue", 0.75, out1)
    generate_sfx_to_file("impact cue", 0.75, out2)

    assert out1.read_bytes() == b"sfx-bytes"
    assert out2.read_bytes() == b"sfx-bytes"
    assert calls["count"] == 1
