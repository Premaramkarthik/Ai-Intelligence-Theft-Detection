"""Runtime configuration for the backend services."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and defaults."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RTSP Camera Backend"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    public_api_base_url: str = "http://localhost:8000"
    public_ws_base_url: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str # = "postgresql://postgres:postgres@localhost:5432/rtsp_camera"
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    run_migrations_on_startup: bool = True

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "rtsp-camera-backend"
    kafka_client_id: str = "rtsp-camera-api"
    kafka_enabled: bool = True
    kafka_topic_camera_status: str = "camera.status"
    kafka_topic_camera_events: str = "camera.events"
    kafka_topic_camera_ai_results: str = "camera.ai_results"
    kafka_topic_camera_tracking_updates: str = "camera.tracking.updates"

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ffmpeg_rtsp_transport: str = "tcp"
    mediamtx_binary: str = "mediamtx"
    mediamtx_manage_process: bool = True
    mediamtx_generated_config_path: Path = BACKEND_ROOT / "runtime" / "mediamtx.generated.yml"
    mediamtx_start_timeout_seconds: float = 8.0
    mediamtx_api_base_url: str = "http://localhost:9997"
    mediamtx_api_timeout_seconds: float = 5.0
    mediamtx_api_ready_timeout_seconds: float = 3.0
    mediamtx_api_username: str = "backend-control"
    mediamtx_api_password: SecretStr | None = None
    mediamtx_api_password_file: Path = BACKEND_ROOT / "runtime" / "mediamtx.api.password"
    mediamtx_rtsp_base_url: str = "rtsp://localhost:8554"
    mediamtx_hls_base_url: str = "http://localhost:8888"
    mediamtx_webrtc_base_url: str = "http://localhost:8889"
    realtime_frame_sample_fps: float = 5.0
    realtime_frame_queue_size: int = 512
    realtime_max_reconnect_attempts: int = 5
    metrics_enabled: bool = True
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9109
    metrics_collection_interval_seconds: float = 5.0
    hls_segment_time_seconds: int = 2
    hls_playlist_size: int = 6
    stream_start_timeout_seconds: int = 12

    worker_monitor_interval_seconds: int = 5
    worker_shutdown_grace_seconds: int = 8
    worker_heartbeat_interval_seconds: int = 10
    reconnect_base_delay_seconds: float = 1.0
    reconnect_max_delay_seconds: float = 15.0

    validation_timeout_seconds: int = 8
    tracking_enabled_by_default: bool = True
    tracking_sample_fps: float = 8.0
    tracking_output_fps: float = 8.0
    tracking_detector_model_id: str = "rfdetr-medium"
    tracking_detector_confidence_threshold: float = 0.45
    tracking_detector_iou_threshold: float = 0.35
    tracking_detector_target_class_name: str = "person"
    tracking_detector_api_key: SecretStr | None = None
    tracking_embedder_name: str = "mobilenet"
    tracking_embedder_weights_path: Path = (
        BACKEND_ROOT
        / "src"
        / "services"
        / "tracking"
        / "reid"
        / "weights"
        / "mobilenetv2_bottleneck_wts.pt"
    )
    tracking_tracker_lost_track_buffer: int = 30         # was 10; 30 frames ≈ 3.75 s at 8 fps
    tracking_tracker_activation_threshold: float = 0.45  # was 0.7; lower avoids false new-person at low conf
    tracking_tracker_minimum_consecutive_frames: int = 3  # was 2; extra stability at 8 fps
    tracking_tracker_minimum_iou_threshold: float = 0.2   # was 0.3; looser match for sampled CCTV
    tracking_tracker_high_conf_det_threshold: float = 0.5
    tracking_identity_store_uri: str = str(BACKEND_ROOT / "runtime" / "milvus_tracking.db")
    tracking_identity_store_token: SecretStr | None = None
    tracking_identity_collection_name: str = "person_tracking_identities"
    tracking_identity_dimension: int = 1280
    tracking_identity_store_timeout_seconds: float = 5.0
    tracking_identity_similarity_threshold: float = 0.75
    tracking_identity_search_limit: int = 5
    tracking_identity_sync_interval_seconds: float = 1.0
    tracking_publish_update_interval_seconds: float = 0.5
    tracking_stream_suffix: str = "tracked"
    log_level: str = "INFO"
    json_logs: bool = False
    file_logs_enabled: bool = True
    log_directory: Path = BACKEND_ROOT / "runtime" / "logs"
    log_file_prefix: str = "backend"
    log_file_max_bytes: int = 10 * 1024 * 1024
    log_file_backup_count: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Normalize comma-separated CORS origins into a list."""

        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: bool | str) -> bool:
        """Parse boolean-like debug environment values."""

        if isinstance(value, bool):
            return value
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
            return False
        raise ValueError("debug must be a boolean-like value.")

    @field_validator("mediamtx_generated_config_path", mode="before")
    @classmethod
    def resolve_mediamtx_generated_config_path(cls, value: str | Path) -> Path:
        """Resolve the generated MediaMTX config path relative to the backend root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_ROOT / path

    @field_validator("mediamtx_api_password_file", mode="before")
    @classmethod
    def resolve_mediamtx_api_password_file(cls, value: str | Path) -> Path:
        """Resolve the MediaMTX Control API password file relative to the backend root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_ROOT / path

    @field_validator("log_directory", mode="before")
    @classmethod
    def resolve_log_directory(cls, value: str | Path) -> Path:
        """Resolve the backend log directory relative to the backend root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_ROOT / path

    @field_validator(
        "tracking_embedder_weights_path",
        mode="before",
    )
    @classmethod
    def resolve_tracking_paths(cls, value: str | Path) -> Path:
        """Resolve tracking asset paths relative to the backend root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_ROOT / path

    @property
    def sql_dir(self) -> Path:
        """Return the directory containing parameterized SQL files."""

        return BACKEND_ROOT / "scripts" / "sql"

    @property
    def migration_dir(self) -> Path:
        """Return the directory containing database migrations."""

        return BACKEND_ROOT / "scripts" / "migrations"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    return Settings()
