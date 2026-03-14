"""
Centralised JSON structured logger using only stdlib logging.

Usage:
    from shared.logging.logger import get_logger
    log = get_logger(__name__)
    log.info("frame processed", extra={"camera_id": "cam01", "latency_ms": 42})
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

import redis

from shared.core.settings import get_settings

class _JsonFormatter(logging.Formatter):
    """Emit every log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict = {
            "ts": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge any structured fields passed via extra={}
        for key, value in record.__dict__.items():
            if key not in (
                "args", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno",
                "message", "module", "msecs", "msg", "name", "pathname",
                "process", "processName", "relativeCreated", "stack_info",
                "taskName", "thread", "threadName",
            ):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class RedisLogHandler(logging.Handler):
    """Publishes logs to a Redis channel."""

    def __init__(self, channel: str = "logs") -> None:
        super().__init__()
        self.channel = channel
        self.redis_client = None

        self._redis_url = get_settings().redis_url
        self._formatter = _JsonFormatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.redis_client is None:
                self.redis_client = redis.from_url(self._redis_url, socket_timeout=1)
            
            message = self._formatter.format(record)
            self.redis_client.publish(self.channel, message)
        except Exception:
            # Silently fail to avoid infinite loops if Redis is down
            pass


def _build_handlers() -> list[logging.Handler]:
    handlers = []
    
    # 1. Stdout Handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(_JsonFormatter())
    handlers.append(stdout_handler)
    
    # 2. Redis Handler (optional/automated)
    if os.getenv("ENABLE_REDIS_LOGS", "true").lower() == "true":
        handlers.append(RedisLogHandler())
        
    return handlers


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Return a named logger with JSON and Redis handlers (idempotent)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        for h in _build_handlers():
            logger.addHandler(h)
        logger.propagate = False
    logger.setLevel(level)
    return logger


# Root pipeline logger
root = get_logger("pipeline")
