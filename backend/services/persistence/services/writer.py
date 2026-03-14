"""DB writer for canonical incident events."""
from __future__ import annotations

import json
import time
from datetime import datetime

from services.persistence.models.events import INSERT_QUERY
from services.persistence.utils.metrics import db_write_latency
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
            )
            db_write_latency.observe(time.perf_counter() - t0)
            log.info("Incident saved", extra={"event_id": event.event_id, "label": event.label})
        except Exception as exc:
            log.error("DB save failed", extra={"error": str(exc), "event_id": event.event_id})
            raise
