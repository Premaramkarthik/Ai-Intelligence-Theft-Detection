from __future__ import annotations

from typing import Any

from src.core.db import Database
from src.models.camera import StreamDesiredState, StreamProtocol, StreamRecord, StreamStatus


class StreamStateRepository:
    """Persistence helper for ``stream_state`` rows."""

    GET_STREAM_SQL = "stream/get_stream.sql"
    UPSERT_STREAM_METADATA_SQL = "stream/upsert_stream_metadata.sql"

    def __init__(self, database: Database) -> None:
        self._database = database

    async def fetch_by_camera_id(self, camera_id: str) -> StreamRecord | None:
        row = await self._database.fetchrow_file(self.GET_STREAM_SQL, camera_id)
        return self._map_stream(row) if row else None

    async def upsert_metadata(
        self,
        camera_id: str,
        metadata: dict[str, Any],
    ) -> StreamRecord:
        row = await self._database.fetchrow_file(
            self.UPSERT_STREAM_METADATA_SQL,
            camera_id,
            metadata,
        )
        return self._map_stream(row)

    @staticmethod
    def _map_stream(row: Any) -> StreamRecord:
        return StreamRecord(
            camera_id=row["camera_id"],
            stream_id=row["stream_id"],
            status=StreamStatus(row["status"]),
            desired_state=StreamDesiredState(row["desired_state"]),
            protocol=StreamProtocol(row["protocol"]),
            playback_path=row["playback_path"],
            playlist_path=row["playlist_path"],
            worker_pid=row["worker_pid"],
            worker_started_at=row["worker_started_at"],
            last_event_at=row["last_event_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
            restart_count=row["restart_count"] or 0,
            reconnect_attempts=row["reconnect_attempts"] or 0,
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
