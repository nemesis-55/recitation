from __future__ import annotations

import json
import logging
import sys
from time import perf_counter
from typing import Any


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[logging.StreamHandler(sys.stdout)],
        format="%(message)s",
    )


def log_event(logger: logging.Logger, stage: str, event: str, **kwargs: Any) -> None:
    payload = {"stage": stage, "event": event, **kwargs}
    logger.info(json.dumps(payload, ensure_ascii=True))


class StageTimer:
    def __init__(self, logger: logging.Logger, stage: str):
        self.logger = logger
        self.stage = stage
        self.start = 0.0

    def __enter__(self) -> "StageTimer":
        self.start = perf_counter()
        log_event(self.logger, self.stage, "start")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = int((perf_counter() - self.start) * 1000)
        if exc is None:
            log_event(self.logger, self.stage, "done", elapsed_ms=elapsed_ms)
        else:
            log_event(self.logger, self.stage, "error", elapsed_ms=elapsed_ms, detail=str(exc))
