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
    kafka_topic_camera_frames: str = "camera.frames"
    kafka_topic_identity_events: str = "identity.events"

    ffprobe_binary: str = "ffprobe"
    metrics_enabled: bool = True
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9109
    metrics_collection_interval_seconds: float = 5.0
    triton_url: str = "localhost:8001"

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
    tracking_identity_max_concurrent_batches: int = 4
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

    opencv_pipeline_enabled: bool = True
    opencv_pipeline_target_width: int = 1280
    opencv_pipeline_target_height: int = 720
    opencv_pipeline_target_fps: float = 10.0
    opencv_pipeline_frame_buffer_size: int = 128
    opencv_pipeline_drop_policy: str = "drop_oldest"
    opencv_pipeline_sync_tolerance_ms: float = 40.0
    opencv_pipeline_batch_size: int = 8
    opencv_pipeline_capture_retry_initial_delay_seconds: float = 0.5
    opencv_pipeline_capture_retry_max_delay_seconds: float = 5.0
    opencv_pipeline_preview_jpeg_quality: int = 70
    opencv_pipeline_publish_frame_previews: bool = False
    opencv_pipeline_low_light_threshold: float = 40.0
    opencv_pipeline_detection_model_path: Path = BACKEND_ROOT / "yolo26n.pt"
    opencv_pipeline_detection_confidence: float = 0.4
    opencv_pipeline_detection_class_ids: list[int] = Field(default_factory=lambda: [0])
    opencv_pipeline_identity_ttl_seconds: float = 30.0
    opencv_pipeline_refresh_all_cameras_interval_seconds: float = 30.0
    opencv_pipeline_calibration_directory: Path = BACKEND_ROOT / "runtime" / "calibration"
    opencv_pipeline_enable_behavior_inference: bool = True
    opencv_pipeline_inference_strategy: str = "cnn_transformer"

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

    @field_validator(
        "opencv_pipeline_detection_model_path",
        "opencv_pipeline_calibration_directory",
        mode="before",
    )
    @classmethod
    def resolve_opencv_pipeline_paths(cls, value: str | Path) -> Path:
        """Resolve OpenCV pipeline asset paths relative to the backend root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_ROOT / path

    @field_validator("opencv_pipeline_detection_class_ids", mode="before")
    @classmethod
    def parse_detection_class_ids(cls, value: str | list[int]) -> list[int]:
        """Normalize detection class ids from env-friendly strings."""

        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value

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
