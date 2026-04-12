"""Structured logging helpers for the inference pipeline."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


def log_inference_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit one structured inference log event."""

    logger.log(
        level,
        message,
        extra={"structured": {"event": event, **fields}},
    )


def log_inference_exception(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    exc: BaseException,
    **fields: Any,
) -> None:
    """Emit one structured inference exception log event and mark the error."""

    mark_exception_logged(exc)
    logger.log(
        level,
        message,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "structured": {
                "event": event,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                **fields,
            },
        },
    )


def summarize_array(array: Any) -> dict[str, object]:
    """Return a compact JSON-safe summary for a numpy-like array."""

    shape = getattr(array, "shape", None)
    dtype = getattr(array, "dtype", None)
    if shape is None:
        return {"type": type(array).__name__}
    return {
        "shape": [int(dimension) for dimension in shape],
        "dtype": str(dtype) if dtype is not None else type(array).__name__,
    }


def summarize_named_arrays(arrays: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    """Summarize a mapping of Triton input/output tensors."""

    return {
        str(name): summarize_array(array)
        for name, array in arrays.items()
    }


def summarize_frame_batch(frames: Sequence[Any], sample_limit: int = 3) -> dict[str, object]:
    """Summarize a list of frame crops without logging raw pixel data."""

    return {
        "frame_count": len(frames),
        "sample_frames": [summarize_array(frame) for frame in frames[:sample_limit]],
    }


def summarize_sample(sample: Any) -> dict[str, object]:
    """Return a compact JSON-safe summary for one ingress sample."""

    sampled_at = getattr(sample, "sampled_at", None)
    crop = getattr(sample, "crop", None)
    summary: dict[str, object] = {
        "camera_id": getattr(sample, "camera_id", None),
        "stream_name": getattr(sample, "stream_name", None),
        "local_track_id": getattr(sample, "local_track_id", None),
        "persistent_id": getattr(sample, "persistent_id", None),
        "persistent_id_state": getattr(sample, "persistent_id_state", None),
        "left": getattr(sample, "left", None),
        "top": getattr(sample, "top", None),
        "width": getattr(sample, "width", None),
        "height": getattr(sample, "height", None),
        "age_frames": getattr(sample, "age_frames", None),
        "consecutive_hits": getattr(sample, "consecutive_hits", None),
        "frames_since_update": getattr(sample, "frames_since_update", None),
    }
    if isinstance(sampled_at, datetime):
        summary["sampled_at"] = sampled_at.isoformat()
    if crop is not None:
        summary["crop"] = summarize_array(crop)
    return {
        key: value
        for key, value in summary.items()
        if value is not None
    }


def summarize_sample_batch(samples: Sequence[Any], sample_limit: int = 3) -> dict[str, object]:
    """Summarize a list of ingress samples without logging raw crops."""

    summary: dict[str, object] = {
        "sample_count": len(samples),
        "sample_tracks": [
            summarize_sample(sample)
            for sample in samples[:sample_limit]
        ],
    }
    if samples:
        first_sampled_at = getattr(samples[0], "sampled_at", None)
        last_sampled_at = getattr(samples[-1], "sampled_at", None)
        if isinstance(first_sampled_at, datetime):
            summary["sampled_at_start"] = first_sampled_at.isoformat()
        if isinstance(last_sampled_at, datetime):
            summary["sampled_at_end"] = last_sampled_at.isoformat()
    return summary


def mark_exception_logged(exc: BaseException) -> None:
    """Mark an exception so outer callers can avoid duplicate stack traces."""

    setattr(exc, "_inference_logged", True)


def was_exception_logged(exc: BaseException) -> bool:
    """Return whether an exception already emitted a structured error log."""

    return bool(getattr(exc, "_inference_logged", False))
