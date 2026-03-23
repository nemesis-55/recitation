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
        # Order: package-local overrides, then repo-root `.env` (user secrets).
        # Do not add a cwd-relative ".env" here: running uvicorn from `manga_video_pipeline/`
        # would load that folder's `.env` last and empty keys could override the repo root.
        env_file=(
            str(_PIPELINE_ROOT / ".env"),
            str(_PROJECT_ROOT / ".env"),
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
    # Accent preset for ElevenLabs TTS (voice IDs still dominate; use Indian English voices from the library).
    # Values: default | indian_english
    elevenlabs_tts_accent: str = Field(default="default", alias="ELEVENLABS_TTS_ACCENT")
    # Lower stability + line context = less "flat/robotic" (ElevenLabs: lower stability = more prosody range).
    elevenlabs_tts_humanize: bool = Field(default=True, alias="ELEVENLABS_TTS_HUMANIZE")
    # 1.0 = default model speed; slightly below 1.0 often sounds more natural for narration.
    elevenlabs_tts_speech_speed: float = Field(default=0.97, alias="ELEVENLABS_TTS_SPEECH_SPEED")
    # Gender-unified base TTS tempo (all male_* share male; all female_* share female). Emotion only nudges.
    elevenlabs_tts_speed_male: float = Field(default=0.98, ge=0.7, le=1.2, alias="ELEVENLABS_TTS_SPEED_MALE")
    elevenlabs_tts_speed_female: float = Field(default=0.98, ge=0.7, le=1.2, alias="ELEVENLABS_TTS_SPEED_FEMALE")
    elevenlabs_tts_speed_unknown: float = Field(default=0.97, ge=0.7, le=1.2, alias="ELEVENLABS_TTS_SPEED_UNKNOWN")
    elevenlabs_tts_speed_narrator: float = Field(default=0.96, ge=0.7, le=1.2, alias="ELEVENLABS_TTS_SPEED_NARRATOR")
    # How much emotion rules can deviate tempo from the gender base (0 = identical tempo per gender).
    elevenlabs_tts_emotion_speed_mix: float = Field(default=0.38, ge=0.0, le=1.0, alias="ELEVENLABS_TTS_EMOTION_SPEED_MIX")
    # Pass adjacent subtitle lines as previous_text/next_text for smoother phrasing (small latency cost).
    elevenlabs_tts_line_context: bool = Field(default=True, alias="ELEVENLABS_TTS_LINE_CONTEXT")
    # Collapse stretched letters (wooooo), pinyin hints (hui→huei) before TTS.
    tts_narration_normalize_enabled: bool = Field(default=True, alias="TTS_NARRATION_NORMALIZE_ENABLED")
    # 0 = best quality / no streaming latency tricks (see ElevenLabs optimize_streaming_latency).
    elevenlabs_tts_optimize_streaming_latency: int = Field(default=0, alias="ELEVENLABS_TTS_OPTIMIZE_STREAMING_LATENCY")
    tts_provider_order: str = Field(default="elevenlabs", alias="TTS_PROVIDER_ORDER")
    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")
    use_mock_llm: bool = Field(default=False, alias="USE_MOCK_LLM")
    use_mock_video: bool = Field(default=False, alias="USE_MOCK_VIDEO")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # When set, audio pipeline / mixer append NDJSON diagnostic lines (debug only; leave unset in prod).
    pipeline_debug_ndjson_path: Optional[str] = Field(default=None, alias="PIPELINE_DEBUG_NDJSON_PATH")

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
    # Persisted pool of local beds (default under outputs/cache/bgm_library). Lazy-filled per slot.
    bgm_library_dir: Optional[str] = Field(default=None, alias="BGM_LIBRARY_DIR")
    bgm_library_count: int = Field(default=10, ge=1, le=64, alias="BGM_LIBRARY_COUNT")
    # When True, use the local library before per-scene ElevenLabs generation (saves cost; repeatable).
    bgm_library_prefer_local: bool = Field(default=True, alias="BGM_LIBRARY_PREFER_LOCAL")
    video_playback_speed: float = Field(default=1.2, ge=0.25, le=4.0, alias="VIDEO_PLAYBACK_SPEED")
    reel_playback_speed: float = Field(default=1.2, ge=0.25, le=4.0, alias="REEL_PLAYBACK_SPEED")
    # Smoother panel concat: libx264 quality when merging clip segments (before mux).
    video_concat_crf: int = Field(default=19, ge=15, le=28, alias="VIDEO_CONCAT_CRF")
    video_concat_preset: str = Field(default="medium", alias="VIDEO_CONCAT_PRESET")
    # Final mux / narration AAC bitrate (YouTube-friendly; higher = cleaner speech bed).
    video_mux_audio_bitrate_k: int = Field(default=192, ge=96, le=320, alias="VIDEO_MUX_AUDIO_BITRATE_K")
    youtube_target_width: int = Field(default=1920, alias="YOUTUBE_TARGET_WIDTH")
    youtube_target_height: int = Field(default=1080, alias="YOUTUBE_TARGET_HEIGHT")
    run_keep_intermediate_clips: bool = Field(default=False, alias="RUN_KEEP_INTERMEDIATE_CLIPS")
    run_keep_video_intermediates: bool = Field(default=False, alias="RUN_KEEP_VIDEO_INTERMEDIATES")
    reel_chunk_max_duration_sec: float = Field(default=60.0, alias="REEL_CHUNK_MAX_DURATION_SEC")
    # Panel clips: fade in/out at cuts (seconds per edge; capped vs short panels).
    panel_transition_fade_sec: float = Field(default=0.15, ge=0.0, le=0.45, alias="PANEL_TRANSITION_FADE_SEC")
    # YouTube: single full panel in 16:9 (1920×1080), safe margins + optional gentle Ken Burns (see panel_animator).
    panel_youtube_zoom_motion: bool = Field(default=True, alias="PANEL_YOUTUBE_ZOOM_MOTION")
    # Multiplier on YouTube landscape Ken Burns amplitude (lower = calmer; better for small screens).
    panel_youtube_motion_amp_scale: float = Field(default=0.62, ge=0.2, le=1.2, alias="PANEL_YOUTUBE_MOTION_AMP_SCALE")
    # Ken Burns zoom-in from center (1.0 = none). ~1.08–1.12 matches typical manga YouTube scans.
    panel_youtube_ken_burns_zoom: float = Field(default=1.09, ge=1.0, le=1.22, alias="PANEL_YOUTUBE_KEN_BURNS_ZOOM")
    # Blurred full-frame background (same panel, cover + heavy blur) behind the sharp panel — recap style.
    panel_youtube_blur_background_enabled: bool = Field(default=True, alias="PANEL_YOUTUBE_BLUR_BACKGROUND_ENABLED")
    panel_youtube_blur_background_sigma: float = Field(default=26.0, ge=4.0, le=80.0, alias="PANEL_YOUTUBE_BLUR_BACKGROUND_SIGMA")
    # Optional darkening of the blurred layer (0 = off; ~0.12–0.22 helps readability).
    panel_youtube_blur_background_brightness: float = Field(default=0.0, ge=0.0, le=0.45, alias="PANEL_YOUTUBE_BLUR_BACKGROUND_BRIGHTNESS")
    # Comma-separated rotation of motion presets per panel (see panel_animator YOUTUBE_MOTION_*).
    panel_youtube_motion_rotation: str = Field(
        default="center_zoom_out,ken_burns,static,slow_drift",
        alias="PANEL_YOUTUBE_MOTION_ROTATION",
    )
    # Reel: scale+center-crop to 1080×1920 (true full-screen Shorts/TikTok style; no pillarboxing).
    panel_reel_full_bleed: bool = Field(default=True, alias="PANEL_REEL_FULL_BLEED")
    # Reel-only motion (defaults True). Independent from YouTube landscape motion.
    panel_reel_zoom_motion: bool = Field(default=True, alias="PANEL_REEL_ZOOM_MOTION")
    # Panel art uses this fraction of the output frame (0.92 ≈ 8% uniform margin; YouTube + reel).
    panel_screen_fill_ratio: float = Field(default=0.92, ge=0.5, le=1.0, alias="PANEL_SCREEN_FILL_RATIO")
    # Multiplier on reel vertical motion amplitude (1.0 = legacy; lower = calmer, easier to read).
    panel_reel_motion_amp_scale: float = Field(default=0.85, ge=0.3, le=1.5, alias="PANEL_REEL_MOTION_AMP_SCALE")
    panel_reel_ken_burns_zoom: float = Field(default=1.10, ge=1.0, le=1.28, alias="PANEL_REEL_KEN_BURNS_ZOOM")

    audio_bed_in_narration: bool = Field(default=True, alias="AUDIO_BED_IN_NARRATION")
    audio_music_local_map_json: Optional[str] = Field(default=None, alias="AUDIO_MUSIC_LOCAL_MAP_JSON")
    audio_music_volume: float = Field(default=0.12, alias="AUDIO_MUSIC_VOLUME")
    audio_use_bgm_default_as_bed: bool = Field(default=True, alias="AUDIO_USE_BGM_DEFAULT_AS_BED")
    audio_ambience_path: Optional[str] = Field(default=None, alias="AUDIO_AMBIENCE_PATH")
    audio_ambience_volume: float = Field(default=0.08, alias="AUDIO_AMBIENCE_VOLUME")
    audio_sfx_volume: float = Field(default=0.16, alias="AUDIO_SFX_VOLUME")
    audio_scene_bridge_enabled: bool = Field(default=False, alias="AUDIO_SCENE_BRIDGE_ENABLED")
    audio_voice_fx_enabled: bool = Field(default=True, alias="AUDIO_VOICE_FX_ENABLED")
    audio_grouping_enabled: bool = Field(default=True, alias="AUDIO_GROUPING_ENABLED")
    audio_panel_wise_mode: bool = Field(default=True, alias="AUDIO_PANEL_WISE_MODE")
    audio_strict_per_line_tts: bool = Field(default=False, alias="AUDIO_STRICT_PER_LINE_TTS")
    audio_group_max_chars: int = Field(default=220, alias="AUDIO_GROUP_MAX_CHARS")
    elevenlabs_voice_map_json: Optional[str] = Field(default=None, alias="ELEVENLABS_VOICE_MAP_JSON")
    elevenlabs_character_profiles_json: Optional[str] = Field(default=None, alias="ELEVENLABS_CHARACTER_PROFILES_JSON")

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
    openai_sfx_alignment_model: Optional[str] = Field(default=None, alias="OPENAI_SFX_ALIGNMENT_MODEL")
    openai_dialogue_batch_size: int = Field(default=6, alias="OPENAI_DIALOGUE_BATCH_SIZE")
    openai_emotion_refine_max_lines: int = Field(default=4, alias="OPENAI_EMOTION_REFINE_MAX_LINES")
    openai_dialogue_batch_pace_sec: float = Field(default=0.35, alias="OPENAI_DIALOGUE_BATCH_PACE_SEC")
    openai_dialogue_min_request_interval_sec: float = Field(default=0.55, alias="OPENAI_DIALOGUE_MIN_REQUEST_INTERVAL_SEC")
    openai_dialogue_rate_limit_cooldown_sec: float = Field(default=0.8, alias="OPENAI_DIALOGUE_RATE_LIMIT_COOLDOWN_SEC")
    # Rewrite OCR into short spoken narration (strip social UI, hashtags read as prose cap).
    openai_narration_polish_enabled: bool = Field(default=True, alias="OPENAI_NARRATION_POLISH_ENABLED")
    openai_narration_polish_model: Optional[str] = Field(default=None, alias="OPENAI_NARRATION_POLISH_MODEL")
    openai_narration_polish_batch_size: int = Field(default=8, ge=1, le=24, alias="OPENAI_NARRATION_POLISH_BATCH_SIZE")
    narration_polish_max_words: int = Field(default=22, ge=8, le=48, alias="NARRATION_POLISH_MAX_WORDS")
    narration_polish_style: str = Field(default="literary_compact", alias="NARRATION_POLISH_STYLE")
    openai_ocr_batch_pace_sec: float = Field(default=0.35, alias="OPENAI_OCR_BATCH_PACE_SEC")
    scene_segment_window_size: int = Field(default=220, alias="SCENE_SEGMENT_WINDOW_SIZE")
    scene_segment_overlap: int = Field(default=16, alias="SCENE_SEGMENT_OVERLAP")
    scene_segment_fallback_gap_sec: float = Field(default=1.2, alias="SCENE_SEGMENT_FALLBACK_GAP_SEC")

    elevenlabs_sfx_enabled: bool = Field(default=False, alias="ELEVENLABS_SFX_ENABLED")
    audio_sfx_alignment_ai_enabled: bool = Field(default=False, alias="AUDIO_SFX_ALIGNMENT_AI_ENABLED")
    audio_sfx_alignment_ai_max_chars: int = Field(default=280, alias="AUDIO_SFX_ALIGNMENT_AI_MAX_CHARS")
    audio_sfx_alignment_ai_min_confidence: float = Field(default=0.45, alias="AUDIO_SFX_ALIGNMENT_AI_MIN_CONFIDENCE")
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
    audio_mixer_use_loudnorm: bool = Field(default=True, alias="AUDIO_MIXER_USE_LOUDNORM")
    audio_mixer_highpass_hz: int = Field(default=80, alias="AUDIO_MIXER_HIGHPASS_HZ")
    audio_mixer_lowpass_hz: int = Field(default=12000, alias="AUDIO_MIXER_LOWPASS_HZ")
    # Music bed only (before duck + master bus): carve out low mud vs voice; 0 = disable HPF on bed.
    audio_mixer_music_highpass_hz: int = Field(default=100, ge=0, le=500, alias="AUDIO_MIXER_MUSIC_HIGHPASS_HZ")
    # Level uneven library / generated beds before sidechain ducking (does not shift timeline).
    audio_mixer_music_dynaudnorm_enabled: bool = Field(default=True, alias="AUDIO_MIXER_MUSIC_DYNAUDNORM_ENABLED")
    # Crossfade between scene narration MP3s when merging (0 = plain concat demuxer). Timeline offsets adjust.
    audio_scene_crossfade_sec: float = Field(default=0.06, ge=0.0, le=0.5, alias="AUDIO_SCENE_CROSSFADE_SEC")
    audio_narration_enhance_enabled: bool = Field(default=True, alias="AUDIO_NARRATION_ENHANCE_ENABLED")
    audio_narration_enhance_max_per_scene: int = Field(default=2, alias="AUDIO_NARRATION_ENHANCE_MAX_PER_SCENE")
    audio_narration_enhance_min_intensity: float = Field(default=0.62, alias="AUDIO_NARRATION_ENHANCE_MIN_INTENSITY")

    elevenlabs_sts_enabled: bool = Field(default=False, alias="ELEVENLABS_STS_ENABLED")
    elevenlabs_sts_model_id: str = Field(default="eleven_multilingual_sts_v2", alias="ELEVENLABS_STS_MODEL_ID")
    elevenlabs_sts_remove_background_noise: bool = Field(default=True, alias="ELEVENLABS_STS_REMOVE_BACKGROUND_NOISE")
    elevenlabs_sts_intensity_threshold: float = Field(default=0.88, alias="ELEVENLABS_STS_INTENSITY_THRESHOLD")
    webtoon_catalog_enabled: bool = Field(default=False, alias="WEBTOON_CATALOG_ENABLED")
    webtoon_catalog_file: str = Field(default="webtoon_catalog.json", alias="WEBTOON_CATALOG_FILE")
    webtoon_catalog_genre_urls_json: Optional[str] = Field(default=None, alias="WEBTOON_CATALOG_GENRE_URLS_JSON")
    webtoon_catalog_request_timeout_sec: int = Field(default=25, alias="WEBTOON_CATALOG_REQUEST_TIMEOUT_SEC")
    webtoon_catalog_max_titles_per_genre: int = Field(default=80, alias="WEBTOON_CATALOG_MAX_TITLES_PER_GENRE")
    # Upper bound per series after pagination (raise if you need very long runs).
    webtoon_catalog_max_episodes_per_title: int = Field(default=999, ge=1, le=500000, alias="WEBTOON_CATALOG_MAX_EPISODES_PER_TITLE")
    # LINE Webtoon list pages often paginate with `page=` — fetch until empty or cap.
    webtoon_catalog_max_list_pages: int = Field(default=50, ge=1, le=200, alias="WEBTOON_CATALOG_MAX_LIST_PAGES")
    webtoon_catalog_workers: int = Field(default=10, alias="WEBTOON_CATALOG_WORKERS")
    webtoon_catalog_refresh_max_age_hours: int = Field(default=24, alias="WEBTOON_CATALOG_REFRESH_MAX_AGE_HOURS")
    subtitle_strict_from_script: bool = Field(default=True, alias="SUBTITLE_STRICT_FROM_SCRIPT")
    enable_cache: bool = Field(default=True, alias="ENABLE_CACHE")
    auto_chunk_enabled: bool = Field(default=False, alias="AUTO_CHUNK_ENABLED")
    auto_chunk_max_panels: int = Field(default=80, alias="AUTO_CHUNK_MAX_PANELS")
    auto_chunk_stitch: bool = Field(default=True, alias="AUTO_CHUNK_STITCH")
    auto_chunk_max_chunks: int = Field(default=20, alias="AUTO_CHUNK_MAX_CHUNKS")


settings = Settings()
