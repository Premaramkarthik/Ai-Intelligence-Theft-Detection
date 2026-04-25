from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


@dataclass(slots=True, frozen=True)
class _SubsystemLogSpec:
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
    _SubsystemLogSpec(
        name="prediction",
        logger_prefixes=("src.services.inference.prediction",),
        structured_event_prefixes=("inference.prediction_",),
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


def _matches_logger_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


class _AioiceLinkLocalFilter(logging.Filter):
    """Drop aioice INFO records about link-local (169.254.x.x) bind failures on Windows.

    These addresses are APIPA addresses that Windows cannot bind to. aioice logs
    each failed attempt at INFO level, producing noise in every WebRTC session even
    though ICE still completes successfully via valid interfaces.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "Could not bind to 169.254" not in record.getMessage()


class _SubsystemLogFilter(logging.Filter):
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
        if any(_matches_logger_prefix(record.name, p) for p in self._logger_prefixes):
            return True
        structured = getattr(record, "structured", None)
        if not isinstance(structured, dict):
            return False
        event = structured.get("event")
        if not isinstance(event, str):
            return False
        return any(
            event == p or event.startswith(p)
            for p in self._structured_event_prefixes
        )


def _rotating_handler(
    path: Path,
    formatter: logging.Formatter,
    max_bytes: int,
    backup_count: int,
    log_filter: logging.Filter | None = None,
) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=max(max_bytes, 1),
        backupCount=max(backup_count, 0),
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(formatter)
    if log_filter is not None:
        handler.addFilter(log_filter)
    return handler


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
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(level.upper())
    root.propagate = False

    formatter = _create_formatter(json_logs)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # Suppress noisy link-local bind warnings from aioice on Windows.
    if sys.platform == "win32":
        logging.getLogger("aioice.ice").addFilter(_AioiceLinkLocalFilter())

    log_dir = Path(log_directory) if log_directory is not None else Path.cwd() / "runtime" / "logs"

    if enable_file_logging:
        root.addHandler(
            _rotating_handler(
                log_dir / "all.log",
                formatter,
                log_file_max_bytes,
                log_file_backup_count,
            )
        )

    if enable_subsystem_file_logging:
        for subsystem in SUBSYSTEM_LOG_SPECS:
            root.addHandler(
                _rotating_handler(
                    log_dir / f"{subsystem.name}.log",
                    formatter,
                    log_file_max_bytes,
                    log_file_backup_count,
                    log_filter=_SubsystemLogFilter(
                        logger_prefixes=subsystem.logger_prefixes,
                        structured_event_prefixes=subsystem.structured_event_prefixes,
                    ),
                )
            )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
