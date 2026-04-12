from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from multiprocessing import current_process
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(structured)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _create_formatter(json_logs: bool) -> logging.Formatter:
    if json_logs:
        return JsonFormatter()
    return logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%dT%H:%M:%S%z",
    )


def _sanitize_path_token(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("._-")
    return sanitized or "process"


def _resolve_log_file_path(log_directory: Path, log_file_prefix: str) -> Path:
    process_name = _sanitize_path_token(current_process().name or "process")
    process_directory = log_directory / process_name
    process_directory.mkdir(parents=True, exist_ok=True)
    file_name = f"{_sanitize_path_token(log_file_prefix)}-{os.getpid()}.log"
    return process_directory / file_name


def configure_logging(
    level: str,
    json_logs: bool = False,
    *,
    enable_file_logging: bool = False,
    log_directory: str | Path | None = None,
    log_file_prefix: str = "backend",
    log_file_max_bytes: int = 10 * 1024 * 1024,
    log_file_backup_count: int = 5,
) -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(level.upper())
    root_logger.propagate = False

    formatter = _create_formatter(json_logs)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if enable_file_logging:
        resolved_log_directory = Path(log_directory) if log_directory is not None else (
            Path.cwd() / "runtime" / "logs"
        )
        log_file_path = _resolve_log_file_path(
            resolved_log_directory,
            log_file_prefix=log_file_prefix,
        )
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max(log_file_max_bytes, 1),
            backupCount=max(log_file_backup_count, 0),
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
