"""DB Writer — handles inserts and evidence storage."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from shared.logging.logger import get_logger
from shared.db.session import DatabaseSession
from services.persistence.models.events import INSERT_QUERY
from services.persistence.utils.metrics import db_write_latency

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
        try:
            pool = self._db.get_pool()
            await pool.execute(
                INSERT_QUERY,
                data.get("camera_id"),
                data.get("trace_id", "0"),
                data.get("label") or data.get("class_name"), # Support both
                data.get("confidence"),
                data.get("evidence_path") or data.get("evidence_uri", ""),
                datetime.fromtimestamp(data.get("ts", time.time()), tz=timezone.utc),
                data.get("t_capture", 0),
                data.get("t_output", 0),
            )
            elapsed = time.perf_counter() - t0
            db_write_latency.observe(elapsed)
            log.info("Event saved", extra={"label": data.get("label"), "latency": elapsed})
        except Exception as exc:
            log.error("DB Save failed", extra={"error": str(exc)})
