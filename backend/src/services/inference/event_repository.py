"""Persist non-normal inference alerts to the inference_events table."""

from __future__ import annotations

import logging
from datetime import datetime

import asyncpg

from src.core.logger.logger import get_logger
from src.services.inference.logging import log_inference_event


class InferenceEventRepository:
    """Write non-normal inference alert rows via the asyncpg connection pool.

    Only ``warning`` and ``alert`` level results are persisted; ``normal``
    results are discarded to keep write volume manageable (plan §3.11).
    """

    _INSERT = """
        INSERT INTO inference_events (
            camera_id,
            stream_name,
            persistent_id,
            local_track_id,
            strategy,
            score,
            alert_level,
            label,
            model_name,
            sampled_at,
            emitted_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._logger = get_logger(__name__)

    async def save(
        self,
        *,
        camera_id: str,
        stream_name: str,
        persistent_id: str,
        local_track_id: str,
        strategy: str,
        score: float,
        alert_level: str,
        label: str,
        model_name: str,
        sampled_at: datetime,
        emitted_at: datetime,
    ) -> None:
        """Insert one inference alert row.  Silently drops ``normal`` records."""
        if alert_level == "normal":
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    self._INSERT,
                    camera_id,
                    stream_name,
                    persistent_id,
                    local_track_id,
                    strategy,
                    score,
                    alert_level,
                    label,
                    model_name,
                    sampled_at,
                    emitted_at,
                )
        except asyncpg.PostgresError as exc:
            log_inference_event(
                self._logger,
                logging.ERROR,
                "inference.persistence_failed",
                "Failed to persist inference event.",
                camera_id=camera_id,
                stream_name=stream_name,
                persistent_id=persistent_id,
                local_track_id=local_track_id,
                strategy=strategy,
                model_name=model_name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
