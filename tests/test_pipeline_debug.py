"""Optional NDJSON pipeline diagnostics (off by default)."""

from pathlib import Path
from types import SimpleNamespace

from app.utils import pipeline_debug as pd
from app.utils.pipeline_debug import log_pipeline_debug


def test_log_pipeline_debug_noop_when_path_unset(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pd, "settings", SimpleNamespace(pipeline_debug_ndjson_path=None))
    out = tmp_path / "should_not_exist.ndjson"
    log_pipeline_debug("r1", "H1", "loc", "msg", {"x": 1})
    assert not out.exists()


def test_log_pipeline_debug_writes_when_path_set(monkeypatch, tmp_path: Path):
    out = tmp_path / "dbg.ndjson"
    monkeypatch.setattr(pd, "settings", SimpleNamespace(pipeline_debug_ndjson_path=str(out)))
    log_pipeline_debug("r1", "H1", "loc", "msg", {"x": 2})
    text = out.read_text(encoding="utf-8").strip()
    assert '"runId": "r1"' in text
    assert '"x": 2' in text
