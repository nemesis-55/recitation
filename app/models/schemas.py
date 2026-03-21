from __future__ import annotations

from typing import Any, Literal
from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    pdf_path: str = Field(..., description="Absolute or relative path to a manga PDF file.")
    subtitles: bool = Field(default=True)
    target_duration_sec: Optional[int] = Field(default=None, ge=30, le=180)
    max_panels: Optional[int] = Field(default=None, ge=1, le=500)
    bgm_path: Optional[str] = None


class GenerateResponse(BaseModel):
    status: Literal["completed", "failed"]
    video_path: Optional[str] = None
    stage: Optional[str] = None
    provider: Optional[str] = None
    error_code: Optional[str] = None
    error: Optional[str] = None
    report_path: Optional[str] = None


class PageAsset(BaseModel):
    page_index: int
    image_path: str
    width: int
    height: int


class PanelAsset(BaseModel):
    page_index: int
    panel_index: int
    image_path: str
    bbox: tuple[int, int, int, int]
    confidence: float = 0.0


class OcrResult(BaseModel):
    panel_path: str
    text: str
    confidence: float
    low_confidence: bool = False


class ScriptLine(BaseModel):
    panel_path: str
    narration: str
    speaker: str = "unknown_1"
    gender: str = "unknown"
    emotion: str = "neutral"
    voice: Optional[str] = None


class AudioSegment(BaseModel):
    line_index: int
    audio_path: str
    start_sec: float
    end_sec: float
    duration_sec: float


class TimelineEntry(BaseModel):
    panel_path: str
    clip_path: Optional[str] = None
    narration: str
    start_sec: float
    end_sec: float
    duration_sec: float


class SubtitleEntry(BaseModel):
    index: int
    start_sec: float
    end_sec: float
    text: str


class QualityReport(BaseModel):
    ok: bool
    duration_sec: float
    has_audio: bool
    has_video: bool
    checks: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
