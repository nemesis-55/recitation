from __future__ import annotations

from typing import Any, Literal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pdf_path: str = Field(..., description="Absolute or relative path to a manga PDF file.")
    srt_path: Optional[str] = Field(default=None, description="Optional SRT path for external master timeline.")
    page_from: Optional[int] = Field(default=None, ge=0)
    page_to: Optional[int] = Field(default=None, ge=0)
    panel_from: Optional[int] = Field(default=None, ge=0)
    panel_to: Optional[int] = Field(default=None, ge=0)


class GenerateResponse(BaseModel):
    status: Literal["completed", "failed"]
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    quality: Optional[str] = None
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
    emotion_intensity: Optional[float] = None
    voice: Optional[str] = None
    rendered_text: Optional[str] = None
    pause_sec: Optional[float] = None
    tts_provider: Optional[str] = None


class AudioSegment(BaseModel):
    line_index: int
    audio_path: str
    start_sec: float
    end_sec: float
    duration_sec: float
    pause_sec: float = 0.0
    provider: Optional[str] = None
    voice: Optional[str] = None
    rendered_text: Optional[str] = None


class TimelineEntry(BaseModel):
    panel_path: str
    clip_path: Optional[str] = None
    narration: str
    start_sec: float
    end_sec: float
    duration_sec: float
    # YouTube panel motion preset for this clip (e.g. center_zoom_out, ken_burns); set by timeline_builder rotation.
    youtube_motion: Optional[str] = None


class SubtitleEntry(BaseModel):
    index: int
    start_sec: float
    end_sec: float
    text: str


class SrtTimelineLine(BaseModel):
    index: int
    start_sec: float
    end_sec: float
    text: str
    speaker: str = "unknown_1"
    emotion: str = "neutral"
    intensity: float = 0.5
    performance_text: Optional[str] = None
    panel_path: Optional[str] = None
    sfx_cues: list[str] = Field(default_factory=list)


class CinematicAudioResponse(BaseModel):
    audio_path: str
    timeline: list[dict[str, Any]]
    quality: Literal["cinematic"]


class MangaSearchResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    updated_at: Optional[str] = None
    stats: dict[str, Any] = Field(default_factory=dict)


class EpisodeGenerateSpec(BaseModel):
    """One episode to generate, with optional panel subset (no page range)."""

    model_config = ConfigDict(extra="forbid")
    episode_no: int = Field(..., ge=0)
    panel_from: Optional[int] = Field(default=None, ge=0)
    panel_to: Optional[int] = Field(default=None, ge=0)


class EpisodeRangeGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title_slug: str
    episode_from: Optional[int] = Field(default=None, ge=0)
    episode_to: Optional[int] = Field(default=None, ge=0)
    episode_numbers: Optional[list[int]] = None
    select_all_episodes: bool = False
    """Preferred: explicit list with optional per-episode panel ranges (replaces range/checkbox modes)."""
    episode_specs: Optional[list[EpisodeGenerateSpec]] = None
    page_from: Optional[int] = Field(default=None, ge=0)
    page_to: Optional[int] = Field(default=None, ge=0)
    panel_from: Optional[int] = Field(default=None, ge=0)
    panel_to: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _unique_episode_specs(self) -> EpisodeRangeGenerateRequest:
        if not self.episode_specs:
            return self
        nos = [s.episode_no for s in self.episode_specs]
        if len(nos) != len(set(nos)):
            raise ValueError("episode_specs: duplicate episode_no")
        return self


class EpisodeRangeGenerateResponse(BaseModel):
    status: Literal["completed", "failed", "partial"]
    title_slug: str
    submitted: int
    completed: int
    failed: int
    results: list[dict[str, Any]]


class QualityReport(BaseModel):
    ok: bool
    duration_sec: float
    has_audio: bool
    has_video: bool
    av_delta_sec: float = 0.0
    checks: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
