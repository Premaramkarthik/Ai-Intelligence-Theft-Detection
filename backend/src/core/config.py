from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
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

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "rtsp-camera-backend"
    kafka_client_id: str = "rtsp-camera-api"
    kafka_enabled: bool = True
    kafka_topic_camera_status: str = "camera.status"
    kafka_topic_camera_events: str = "camera.events"
    kafka_topic_camera_ai_results: str = "camera.ai_results"

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
    realtime_max_reconnect_attempts: int = 8
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
    enable_tracker_bridge: bool = False
    tracker_embedder: str | None = None

    log_level: str = "INFO"
    json_logs: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: bool | str) -> bool:
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

    @property
    def sql_dir(self) -> Path:
        return BACKEND_ROOT / "scripts" / "sql"

    @property
    def migration_dir(self) -> Path:
        return BACKEND_ROOT / "scripts" / "migrations"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
