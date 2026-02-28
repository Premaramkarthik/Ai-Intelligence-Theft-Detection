from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os

class Settings(BaseSettings):
    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "karthikS9")
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    @property
    def redis_url(self) -> str:
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # PostgreSQL
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "pipeline_events")
    postgres_user: str = os.getenv("POSTGRES_USER", "pipeline_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_pool_size: int = int(os.getenv("POSTGRES_POOL_SIZE", "10"))

    @property
    def db_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_admin_chat_ids: str = os.getenv("TELEGRAM_ADMIN_CHAT_IDS", "")

    # JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "secret")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    # Signaling
    signaling_host: str = os.getenv("SIGNALING_HOST", "0.0.0.0")
    signaling_port: int = int(os.getenv("SIGNALING_PORT", "9000"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # MediaBridge
    camera_sources: str = os.getenv("CAMERA_SOURCES", "0")  # comma-separated webcam IDs or RTSP URLs
    shm_slots_per_cam: int = int(os.getenv("SHM_SLOTS_PER_CAM", "32"))
    default_input_type: str = os.getenv("DEFAULT_INPUT_TYPE", "rtsp")
    frame_width: int = int(os.getenv("FRAME_WIDTH", "1280"))
    frame_height: int = int(os.getenv("FRAME_HEIGHT", "720"))

    # Model
    model_name: str = os.getenv("MODEL_NAME", "efficient_x3d")
    model_engine_path: str = os.getenv("MODEL_ENGINE_PATH", "")
    model_backend: str = os.getenv("MODEL_BACKEND", "tensorrt")
    temporal_window: int = int(os.getenv("TEMPORAL_WINDOW", "16"))
    default_confidence_threshold: float = float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.7"))
    staleness_limit_ms: int = int(os.getenv("STALENESS_LIMIT_MS", "150"))
    heartbeat_interval_ms: int = int(os.getenv("HEARTBEAT_INTERVAL_MS", "500"))

    # Person Detector
    person_detector_engine: str = os.getenv("PERSON_DETECTOR_ENGINE", "")
    person_conf_threshold: float = float(os.getenv("PERSON_CONF_THRESHOLD", "0.5"))
    person_input_size: int = int(os.getenv("PERSON_INPUT_SIZE", "640"))

    # Item Detection
    item_detector_engine: str = os.getenv("ITEM_DETECTOR_ENGINE", "")
    item_detect_every_n_frames: int = int(os.getenv("ITEM_DETECT_EVERY_N_FRAMES", "5"))
    item_watch_classes: str = os.getenv("ITEM_WATCH_CLASSES", "bottle,backpack,handbag")
    item_iou_threshold: float = float(os.getenv("ITEM_IOU_THRESHOLD", "0.15"))
    hand_dist_px: int = int(os.getenv("HAND_DIST_PX", "80"))
    min_displacement_px: int = int(os.getenv("MIN_DISPLACEMENT_PX", "30"))
    interaction_frames: int = int(os.getenv("INTERACTION_FRAMES", "5"))

    # Alerting
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    mqtt_host: str = os.getenv("MQTT_HOST", "mqtt")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    alert_confidence_threshold: float = float(os.getenv("ALERT_CONF_THRESHOLD", "0.8"))

    # Signaling
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin")
    camera_stream_fps: float = float(os.getenv("CAMERA_STREAM_FPS", "15"))

    # Persistence
    persistence_batch_window_ms: int = int(os.getenv("PERSISTENCE_BATCH_WINDOW_MS", "500"))
    evidence_storage_path: str = os.getenv("EVIDENCE_STORAGE_PATH", "/data/evidence")
    evidence_retention_days: int = int(os.getenv("EVIDENCE_RETENTION_DAYS", "30"))

    # Shared / ConfigManager
    config_poll_interval_s: float = float(os.getenv("CONFIG_POLL_INTERVAL_S", "5"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file_path: str = os.getenv("LOG_FILE_PATH", "/var/log/pipeline/pipeline.log")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",)
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
