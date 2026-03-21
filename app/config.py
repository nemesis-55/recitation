from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _APP_DIR.parent
_PROJECT_ROOT = _PIPELINE_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_PIPELINE_ROOT / ".env"),
            str(_PROJECT_ROOT / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    runway_api_key: Optional[str] = Field(default=None, alias="RUNWAY_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="alloy", alias="OPENAI_TTS_VOICE")
    openai_tts_voice_male: str = Field(default="alloy", alias="OPENAI_TTS_VOICE_MALE")
    openai_tts_voice_female: str = Field(default="nova", alias="OPENAI_TTS_VOICE_FEMALE")
    openai_tts_voice_unknown: str = Field(default="echo", alias="OPENAI_TTS_VOICE_UNKNOWN")
    openai_tts_voice_narrator: str = Field(default="onyx", alias="OPENAI_TTS_VOICE_NARRATOR")
    openai_tts_emotion_overrides: str = Field(
        default="angry:shimmer,sad:echo,fear:ash,happy:nova,neutral:onyx",
        alias="OPENAI_TTS_EMOTION_OVERRIDES",
    )
    runway_api_base_url: str = Field(default="https://api.dev.runwayml.com", alias="RUNWAY_API_BASE_URL")
    video_gen_provider: str = Field(default="runway", alias="VIDEO_GEN_PROVIDER")
    tts_provider: str = Field(default="auto", alias="TTS_PROVIDER")
    use_mock_llm: bool = Field(default=False, alias="USE_MOCK_LLM")
    use_mock_video: bool = Field(default=False, alias="USE_MOCK_VIDEO")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    output_root: Path = Field(default=_PIPELINE_ROOT / "outputs", alias="OUTPUT_ROOT")
    runs_dir_name: str = Field(default="runs", alias="RUNS_DIR_NAME")
    default_fps: int = Field(default=30, alias="DEFAULT_FPS")
    default_dpi: int = Field(default=250, alias="DEFAULT_DPI")
    max_pages: int = Field(default=80, alias="MAX_PAGES")
    max_page_megapixels: float = Field(default=14.0, alias="MAX_PAGE_MEGAPIXELS")
    min_free_disk_mb: int = Field(default=1024, alias="MIN_FREE_DISK_MB")

    min_panel_duration_sec: float = Field(default=2.0, alias="MIN_PANEL_DURATION_SEC")
    max_panel_duration_sec: float = Field(default=6.0, alias="MAX_PANEL_DURATION_SEC")
    min_video_duration_sec: int = Field(default=30, alias="MIN_VIDEO_DURATION_SEC")
    max_video_duration_sec: int = Field(default=180, alias="MAX_VIDEO_DURATION_SEC")
    target_width: int = Field(default=1080, alias="TARGET_WIDTH")
    target_height: int = Field(default=1920, alias="TARGET_HEIGHT")

    enable_subtitles_default: bool = Field(default=True, alias="ENABLE_SUBTITLES_DEFAULT")
    bgm_default_path: Optional[str] = Field(default=None, alias="BGM_DEFAULT_PATH")
    bgm_volume: float = Field(default=0.14, alias="BGM_VOLUME")

    stage_timeout_sec: int = Field(default=300, alias="STAGE_TIMEOUT_SEC")
    provider_timeout_sec: int = Field(default=60, alias="PROVIDER_TIMEOUT_SEC")
    provider_retries: int = Field(default=2, alias="PROVIDER_RETRIES")
    openai_ocr_batch_size: int = Field(default=6, alias="OPENAI_OCR_BATCH_SIZE")
    openai_ocr_max_image_dim: int = Field(default=768, alias="OPENAI_OCR_MAX_IMAGE_DIM")
    openai_ocr_jpeg_quality: int = Field(default=72, alias="OPENAI_OCR_JPEG_QUALITY")
    openai_ocr_recovery_batches: int = Field(default=4, alias="OPENAI_OCR_RECOVERY_BATCHES")
    openai_script_batch_size: int = Field(default=12, alias="OPENAI_SCRIPT_BATCH_SIZE")
    openai_debug_io: bool = Field(default=False, alias="OPENAI_DEBUG_IO")
    subtitle_strict_from_script: bool = Field(default=True, alias="SUBTITLE_STRICT_FROM_SCRIPT")
    enable_cache: bool = Field(default=True, alias="ENABLE_CACHE")


settings = Settings()
