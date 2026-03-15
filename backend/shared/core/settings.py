from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_url_env: str = ""

    @property
    def redis_url(self) -> str:
        if self.redis_url_env:
            return self.redis_url_env
        if self.redis_password:
            password = quote(self.redis_password, safe="")
            return f"redis://:{password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "pipeline_events"
    postgres_user: str = "pipeline_user"
    postgres_password: str = ""
    postgres_pool_size: int = 10

    @property
    def db_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Telegram
    telegram_bot_token: str = ""
    telegram_admin_chat_ids: str = ""

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    auth_cookie_name: str = "pipeline_access_token"
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_cookie_secure: bool = False
    enable_api_docs: bool = False

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    expose_metrics_api: bool = False
    metrics_bind_host: str = "0.0.0.0"
    metrics_token: str = ""

    # MediaBridge
    shm_slots_per_cam: int = 32
    frame_width: int = 1280
    frame_height: int = 720
    frame_queue_maxlen: int = 256
    legacy_global_frame_queue: bool = False
    frame_stale_after_s: float = 3.0
    evidence_dir: str = "/data/evidence"
    default_organization_id: str = "default-org"
    default_store_id: str = "main-store"
    model_version: str = "yolo26n.engine+cnn_transformer.engine"

    # Inference models
    detector_engine_path: str = "models/yolo/yolo26n.engine"
    classifier_engine_path: str = "models/shoplifting/cnn_transformer.engine"
    temporal_window: int = 16
    default_confidence_threshold: float = 0.7
    hand_dist_px: int = 80
    interaction_frames: int = 5

    # Alerting
    alert_confidence_threshold: float = 0.8

    admin_username: str = ""
    admin_password: str = ""
    camera_stream_fps: float = 15.0
    preview_transport: Literal["mjpeg", "webrtc"] = "webrtc"
    webrtc_enabled: bool = True
    webrtc_stun_urls: str = "stun:stun.l.google.com:19302"
    webrtc_turn_url: str = ""
    webrtc_turn_username: str = ""
    webrtc_turn_password: str = ""
    max_preview_viewers_per_camera: int = 8
    preview_frame_rate: float = 10.0
    webrtc_gather_timeout_s: float = 3.0

    config_poll_interval_s: float = 5.0
    allow_private_camera_hosts: bool = True
    reject_loopback_camera_hosts: bool = True
    max_source_url_length: int = 2048
    reid_enabled: bool = False
    reid_backend: Literal["disabled", "pgvector"] = "disabled"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        return str(value or "development").strip().lower()

    @field_validator("auth_cookie_name")
    @classmethod
    def _validate_cookie_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("AUTH_COOKIE_NAME must not be empty")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def secure_cookies(self) -> bool:
        return self.auth_cookie_secure or self.app_env not in {"development", "test"}

    def validate_auth_settings(self, *, require_admin_credentials: bool = False) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be configured and at least 32 characters long")
        if require_admin_credentials and (not self.admin_username or not self.admin_password):
            raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must be configured")
        if "*" in self.cors_origin_list:
            raise RuntimeError("Wildcard CORS is not allowed when credentials are enabled")
        if self.auth_cookie_samesite == "none" and not self.secure_cookies:
            raise RuntimeError("SameSite=None cookies require AUTH_COOKIE_SECURE=true")


@lru_cache
def get_settings() -> Settings:
    return Settings()
