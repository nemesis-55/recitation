"""
Optional newline-delimited JSON logging for pipeline diagnostics.

Set PIPELINE_DEBUG_NDJSON_PATH to a file path to append one JSON object per log line.
When unset, all logging calls are no-ops (default for production/tests).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import settings


def log_pipeline_debug(
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    *,
    session_id: str = "pipeline",
) -> None:
    """Append one NDJSON line if ``PIPELINE_DEBUG_NDJSON_PATH`` is configured."""
    raw = getattr(settings, "pipeline_debug_ndjson_path", None)
    if not raw:
        return
    path = Path(str(raw).strip()).expanduser()
    if not path.parts:
        return
    payload = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, ensure_ascii=True) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        return
