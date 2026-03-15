"""DB writer for canonical incident events."""
from __future__ import annotations

import json
import time
from datetime import datetime

from services.persistence.models.events import INSERT_QUERY
from services.persistence.utils.metrics import db_write_latency, db_writes_failed, db_writes_succeeded
from shared.db.session import DatabaseSession
from shared.logging.logger import get_logger
from shared.types.events import IncidentEvent

log = get_logger(__name__)


class DBWriter:
    def __init__(self) -> None:
        self._db = DatabaseSession()

    async def connect(self) -> None:
        await self._db.connect()

    async def disconnect(self) -> None:
        await self._db.disconnect()

    async def initialize_db(self) -> None:
        await self._db.initialize_db()

    async def ensure_connection(self) -> None:
        try:
            pool = self._db.get_pool()
            await pool.fetchval("SELECT 1")
        except Exception:
            await self._db.disconnect()
            await self._db.connect()

    def get_pool(self):
        return self._db.get_pool()

    async def save_event(self, data: dict) -> None:
        t0 = time.perf_counter()
        event = IncidentEvent.model_validate(data)
        try:
            pool = self._db.get_pool()
            await pool.execute(
                INSERT_QUERY,
                event.event_id,
                event.organization_id,
                event.store_id,
                event.camera_id,
                event.trace_id,
                event.event_type,
                event.label,
                event.confidence,
                event.severity.value,
                datetime.fromisoformat(event.timestamp),
                json.dumps(event.frame_ref.model_dump(mode="json")),
                json.dumps(event.detections, default=lambda item: item.model_dump(mode="json")),
                json.dumps(event.metadata),
                event.schema_version,
                json.dumps(event.model_dump(mode="json")),
                event.evidence_uri,
                event.thumbnail_uri,
                event.review_status.value,
                event.review_note,
                event.model_version,
                event.config_version,
            )
            db_write_latency.observe(time.perf_counter() - t0)
            db_writes_succeeded.inc()
            log.info(
                "Incident saved",
                extra={"event_id": event.event_id, "label": event.label, "trace_id": event.trace_id},
            )
        except Exception as exc:
            db_writes_failed.inc()
            log.error(
                "DB save failed",
                extra={"error": str(exc), "event_id": event.event_id, "trace_id": event.trace_id},
            )
            raise
