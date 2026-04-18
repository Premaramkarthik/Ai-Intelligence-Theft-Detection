from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from multiprocessing import current_process
from pathlib import Path


@dataclass(slots=True, frozen=True)
class _SubsystemLogSpec:
    """Routing rule for one dedicated subsystem log file."""

    name: str
    logger_prefixes: tuple[str, ...] = ()
    structured_event_prefixes: tuple[str, ...] = ()


SUBSYSTEM_LOG_SPECS: tuple[_SubsystemLogSpec, ...] = (
    _SubsystemLogSpec(
        name="streaming",
        logger_prefixes=(
            "src.opencv_pipeline.runtime",
            "src.opencv_pipeline.ingestion",
            "src.opencv_pipeline.output",
            "src.opencv_pipeline.buffering",
            "src.opencv_pipeline.preprocessing",
            "src.opencv_pipeline.motion",
            "src.opencv_pipeline.stabilization",
            "src.opencv_pipeline.calibration",
        ),
    ),
    _SubsystemLogSpec(
        name="person_detection",
        logger_prefixes=("src.opencv_pipeline.detection",),
        structured_event_prefixes=("person_detection.",),
    ),
    _SubsystemLogSpec(
        name="tracker",
        logger_prefixes=(
            "src.opencv_pipeline.tracking",
            "src.services.tracking.trackers",
        ),
        structured_event_prefixes=("tracker.",),
    ),
    _SubsystemLogSpec(
        name="body_inference",
        logger_prefixes=(
            "src.opencv_pipeline.reid",
            "src.services.tracking.reid",
        ),
        structured_event_prefixes=("body_inference.",),
    ),
    _SubsystemLogSpec(
        name="milvus",
        logger_prefixes=(
            "src.opencv_pipeline.identity",
            "src.services.tracking.identity",
        ),
        structured_event_prefixes=("milvus.", "identity."),
    ),
    _SubsystemLogSpec(
        name="inference",
        logger_prefixes=("src.services.inference",),
        structured_event_prefixes=("inference.",),
    ),
)


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


def _matches_logger_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


def _resolve_log_file_path(log_directory: Path, log_file_prefix: str) -> Path:
    process_name = _sanitize_path_token(current_process().name or "process")
    process_directory = log_directory / process_name
    process_directory.mkdir(parents=True, exist_ok=True)
    file_name = f"{_sanitize_path_token(log_file_prefix)}-{os.getpid()}.log"
    return process_directory / file_name


class _SubsystemLogFilter(logging.Filter):
    """Allow a record into a subsystem file when its namespace or event matches."""

    def __init__(
        self,
        *,
        logger_prefixes: tuple[str, ...] = (),
        structured_event_prefixes: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._logger_prefixes = logger_prefixes
        self._structured_event_prefixes = structured_event_prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        if any(_matches_logger_prefix(record.name, prefix) for prefix in self._logger_prefixes):
            return True

        structured = getattr(record, "structured", None)
        if not isinstance(structured, dict):
            return False
        event = structured.get("event")
        if not isinstance(event, str):
            return False
        return any(
            event == prefix or event.startswith(prefix)
            for prefix in self._structured_event_prefixes
        )


def configure_logging(
    level: str,
    json_logs: bool = False,
    *,
    enable_file_logging: bool = False,
    log_directory: str | Path | None = None,
    log_file_prefix: str = "backend",
    log_file_max_bytes: int = 10 * 1024 * 1024,
    log_file_backup_count: int = 5,
    enable_subsystem_file_logging: bool = False,
    subsystem_log_directory: str | Path | None = None,
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

    resolved_log_directory = Path(log_directory) if log_directory is not None else (
        Path.cwd() / "runtime" / "logs"
    )
    if enable_file_logging:
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

    if enable_subsystem_file_logging:
        resolved_subsystem_log_directory = (
            Path(subsystem_log_directory)
            if subsystem_log_directory is not None
            else resolved_log_directory / "subsystems"
        )
        for subsystem in SUBSYSTEM_LOG_SPECS:
            subsystem_directory = (
                resolved_subsystem_log_directory / _sanitize_path_token(subsystem.name)
            )
            file_handler = RotatingFileHandler(
                _resolve_log_file_path(
                    subsystem_directory,
                    log_file_prefix=f"{log_file_prefix}-{subsystem.name}",
                ),
                maxBytes=max(log_file_max_bytes, 1),
                backupCount=max(log_file_backup_count, 0),
                encoding="utf-8",
                delay=True,
            )
            file_handler.addFilter(
                _SubsystemLogFilter(
                    logger_prefixes=subsystem.logger_prefixes,
                    structured_event_prefixes=subsystem.structured_event_prefixes,
                )
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
