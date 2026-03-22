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
    elevenlabs_api_key: Optional[str] = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_api_base_url: str = Field(default="https://api.elevenlabs.io", alias="ELEVENLABS_API_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    elevenlabs_tts_model: str = Field(default="eleven_flash_v2_5", alias="ELEVENLABS_TTS_MODEL")
    elevenlabs_tts_model_fallback: str = Field(default="eleven_turbo_v2_5", alias="ELEVENLABS_TTS_MODEL_FALLBACK")
    elevenlabs_output_format: str = Field(default="mp3_44100_128", alias="ELEVENLABS_OUTPUT_FORMAT")
    elevenlabs_voice_male: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE")
    elevenlabs_voice_male_2: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_2")
    elevenlabs_voice_male_3: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_3")
    elevenlabs_voice_male_4: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_4")
    elevenlabs_voice_male_5: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_5")
    elevenlabs_voice_male_6: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_6")
    elevenlabs_voice_male_7: str = Field(default="pNInz6obpgDQGcFmaJgB", alias="ELEVENLABS_VOICE_MALE_7")
    elevenlabs_voice_female: str = Field(default="EXAVITQu4vr4xnSDxMaL", alias="ELEVENLABS_VOICE_FEMALE")
    elevenlabs_voice_female_2: str = Field(default="EXAVITQu4vr4xnSDxMaL", alias="ELEVENLABS_VOICE_FEMALE_2")
    elevenlabs_voice_female_3: str = Field(default="EXAVITQu4vr4xnSDxMaL", alias="ELEVENLABS_VOICE_FEMALE_3")
    elevenlabs_voice_unknown: str = Field(default="onwK4e9ZLuTAKqWW03F9", alias="ELEVENLABS_VOICE_UNKNOWN")
    elevenlabs_voice_narrator: str = Field(default="TxGEqnHWrfWFTfGW9XjX", alias="ELEVENLABS_VOICE_NARRATOR")
    tts_provider_order: str = Field(default="elevenlabs", alias="TTS_PROVIDER_ORDER")
    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")
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
    bgm_volume: float = Field(default=0.12, alias="BGM_VOLUME")
    video_playback_speed: float = Field(default=1.0, alias="VIDEO_PLAYBACK_SPEED")
    run_keep_intermediate_clips: bool = Field(default=False, alias="RUN_KEEP_INTERMEDIATE_CLIPS")

    audio_bed_in_narration: bool = Field(default=True, alias="AUDIO_BED_IN_NARRATION")
    audio_music_local_map_json: Optional[str] = Field(default=None, alias="AUDIO_MUSIC_LOCAL_MAP_JSON")
    audio_music_volume: float = Field(default=0.12, alias="AUDIO_MUSIC_VOLUME")
    audio_use_bgm_default_as_bed: bool = Field(default=True, alias="AUDIO_USE_BGM_DEFAULT_AS_BED")
    audio_ambience_path: Optional[str] = Field(default=None, alias="AUDIO_AMBIENCE_PATH")
    audio_ambience_volume: float = Field(default=0.08, alias="AUDIO_AMBIENCE_VOLUME")
    audio_sfx_volume: float = Field(default=0.16, alias="AUDIO_SFX_VOLUME")
    audio_voice_fx_enabled: bool = Field(default=True, alias="AUDIO_VOICE_FX_ENABLED")
    audio_grouping_enabled: bool = Field(default=True, alias="AUDIO_GROUPING_ENABLED")
    audio_strict_per_line_tts: bool = Field(default=False, alias="AUDIO_STRICT_PER_LINE_TTS")
    audio_group_max_chars: int = Field(default=220, alias="AUDIO_GROUP_MAX_CHARS")
    elevenlabs_voice_map_json: Optional[str] = Field(default=None, alias="ELEVENLABS_VOICE_MAP_JSON")

    stage_timeout_sec: int = Field(default=300, alias="STAGE_TIMEOUT_SEC")
    provider_timeout_sec: int = Field(default=60, alias="PROVIDER_TIMEOUT_SEC")
    provider_retries: int = Field(default=2, alias="PROVIDER_RETRIES")
    av_sync_max_delta_sec: float = Field(default=0.15, alias="AV_SYNC_MAX_DELTA_SEC")
    openai_ocr_batch_size: int = Field(default=3, alias="OPENAI_OCR_BATCH_SIZE")
    openai_ocr_max_image_dim: int = Field(default=768, alias="OPENAI_OCR_MAX_IMAGE_DIM")
    openai_ocr_jpeg_quality: int = Field(default=72, alias="OPENAI_OCR_JPEG_QUALITY")
    openai_ocr_recovery_batches: int = Field(default=4, alias="OPENAI_OCR_RECOVERY_BATCHES")
    openai_ocr_min_request_interval_sec: float = Field(default=0.8, alias="OPENAI_OCR_MIN_REQUEST_INTERVAL_SEC")
    openai_ocr_rate_limit_cooldown_sec: float = Field(default=0.9, alias="OPENAI_OCR_RATE_LIMIT_COOLDOWN_SEC")
    openai_script_batch_size: int = Field(default=12, alias="OPENAI_SCRIPT_BATCH_SIZE")
    openai_skip_empty_ocr_for_cleaner: bool = Field(default=True, alias="OPENAI_SKIP_EMPTY_OCR_FOR_CLEANER")
    openai_debug_io: bool = Field(default=False, alias="OPENAI_DEBUG_IO")
    srt_require_input: bool = Field(default=True, alias="SRT_REQUIRE_INPUT")
    srt_min_line_duration_sec: float = Field(default=0.25, alias="SRT_MIN_LINE_DURATION_SEC")
    srt_max_line_duration_sec: float = Field(default=15.0, alias="SRT_MAX_LINE_DURATION_SEC")

    openai_dialogue_analysis_enabled: bool = Field(default=True, alias="OPENAI_DIALOGUE_ANALYSIS_ENABLED")
    openai_dialogue_analysis_model: Optional[str] = Field(default=None, alias="OPENAI_DIALOGUE_ANALYSIS_MODEL")
    openai_dialogue_batch_size: int = Field(default=3, alias="OPENAI_DIALOGUE_BATCH_SIZE")
    openai_dialogue_batch_pace_sec: float = Field(default=0.35, alias="OPENAI_DIALOGUE_BATCH_PACE_SEC")
    openai_dialogue_min_request_interval_sec: float = Field(default=0.55, alias="OPENAI_DIALOGUE_MIN_REQUEST_INTERVAL_SEC")
    openai_dialogue_rate_limit_cooldown_sec: float = Field(default=0.8, alias="OPENAI_DIALOGUE_RATE_LIMIT_COOLDOWN_SEC")
    openai_ocr_batch_pace_sec: float = Field(default=0.35, alias="OPENAI_OCR_BATCH_PACE_SEC")

    elevenlabs_sfx_enabled: bool = Field(default=False, alias="ELEVENLABS_SFX_ENABLED")
    elevenlabs_sfx_model_id: str = Field(default="eleven_text_to_sound_v2", alias="ELEVENLABS_SFX_MODEL_ID")
    elevenlabs_sfx_output_format: str = Field(default="mp3_44100_128", alias="ELEVENLABS_SFX_OUTPUT_FORMAT")
    elevenlabs_sfx_prompt_influence: float = Field(default=0.7, alias="ELEVENLABS_SFX_PROMPT_INFLUENCE")

    elevenlabs_music_enabled: bool = Field(default=True, alias="ELEVENLABS_MUSIC_ENABLED")
    elevenlabs_music_model_id: str = Field(default="music_v1", alias="ELEVENLABS_MUSIC_MODEL_ID")
    elevenlabs_music_output_format: str = Field(default="mp3_44100_128", alias="ELEVENLABS_MUSIC_OUTPUT_FORMAT")
    elevenlabs_music_force_instrumental: bool = Field(default=True, alias="ELEVENLABS_MUSIC_FORCE_INSTRUMENTAL")

    audio_mixer_voice_gain: float = Field(default=0.9, alias="AUDIO_MIXER_VOICE_GAIN")
    audio_mixer_sfx_gain: float = Field(default=0.7, alias="AUDIO_MIXER_SFX_GAIN")
    audio_mixer_music_gain: float = Field(default=0.12, alias="AUDIO_MIXER_MUSIC_GAIN")
    audio_mixer_ducking_enabled: bool = Field(default=True, alias="AUDIO_MIXER_DUCKING_ENABLED")
    audio_mixer_ducking_threshold: float = Field(default=0.05, alias="AUDIO_MIXER_DUCKING_THRESHOLD")
    audio_mixer_ducking_ratio: float = Field(default=12.0, alias="AUDIO_MIXER_DUCKING_RATIO")
    audio_mixer_ducking_attack_ms: int = Field(default=50, alias="AUDIO_MIXER_DUCKING_ATTACK_MS")
    audio_mixer_ducking_release_ms: int = Field(default=400, alias="AUDIO_MIXER_DUCKING_RELEASE_MS")
    audio_mixer_normalize_loudness: bool = Field(default=True, alias="AUDIO_MIXER_NORMALIZE_LOUDNESS")

    elevenlabs_sts_enabled: bool = Field(default=False, alias="ELEVENLABS_STS_ENABLED")
    elevenlabs_sts_model_id: str = Field(default="eleven_multilingual_sts_v2", alias="ELEVENLABS_STS_MODEL_ID")
    elevenlabs_sts_remove_background_noise: bool = Field(default=True, alias="ELEVENLABS_STS_REMOVE_BACKGROUND_NOISE")
    elevenlabs_sts_intensity_threshold: float = Field(default=0.88, alias="ELEVENLABS_STS_INTENSITY_THRESHOLD")
    webtoon_catalog_enabled: bool = Field(default=False, alias="WEBTOON_CATALOG_ENABLED")
    webtoon_catalog_file: str = Field(default="webtoon_catalog.json", alias="WEBTOON_CATALOG_FILE")
    webtoon_catalog_genre_urls_json: Optional[str] = Field(default=None, alias="WEBTOON_CATALOG_GENRE_URLS_JSON")
    webtoon_catalog_request_timeout_sec: int = Field(default=25, alias="WEBTOON_CATALOG_REQUEST_TIMEOUT_SEC")
    webtoon_catalog_max_titles_per_genre: int = Field(default=80, alias="WEBTOON_CATALOG_MAX_TITLES_PER_GENRE")
    webtoon_catalog_max_episodes_per_title: int = Field(default=250, alias="WEBTOON_CATALOG_MAX_EPISODES_PER_TITLE")
    webtoon_catalog_workers: int = Field(default=10, alias="WEBTOON_CATALOG_WORKERS")
    webtoon_catalog_refresh_max_age_hours: int = Field(default=24, alias="WEBTOON_CATALOG_REFRESH_MAX_AGE_HOURS")
    subtitle_strict_from_script: bool = Field(default=True, alias="SUBTITLE_STRICT_FROM_SCRIPT")
    enable_cache: bool = Field(default=True, alias="ENABLE_CACHE")
    auto_chunk_enabled: bool = Field(default=False, alias="AUTO_CHUNK_ENABLED")
    auto_chunk_max_panels: int = Field(default=80, alias="AUTO_CHUNK_MAX_PANELS")
    auto_chunk_stitch: bool = Field(default=True, alias="AUTO_CHUNK_STITCH")
    auto_chunk_max_chunks: int = Field(default=20, alias="AUTO_CHUNK_MAX_CHUNKS")


settings = Settings()
