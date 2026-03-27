from __future__ import annotations

from datetime import datetime, timezone

import pytest
from src.schemas.stream_responses import StreamEventPayload
from src.services.stream.stream_repository import StreamRepository


class DummyDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow_file(self, relative_path: str, *params: object):
        self.calls.append((relative_path, params))
        return {
            "camera_id": "cam_123",
            "stream_id": "stream_cam_123",
            "status": "running",
            "desired_state": "running",
            "protocol": "hls",
            "playback_path": "http://localhost:8888/cam_123/index.m3u8",
            "playlist_path": "rtsp://192.168.1.2:8080/h264_ulaw.sdp",
            "worker_pid": 1234,
            "worker_started_at": None,
            "last_event_at": None,
            "last_heartbeat_at": None,
            "last_error_code": None,
            "last_error_message": None,
            "restart_count": 0,
            "reconnect_attempts": 0,
            "metadata": {},
            "created_at": None,
            "updated_at": None,
        }


@pytest.mark.asyncio
async def test_apply_event_accepts_string_enum_values() -> None:
    database = DummyDatabase()
    repository = StreamRepository(database)  # type: ignore[arg-type]
    event = StreamEventPayload(
        camera_id="cam_123",
        camera_name="Front Gate",
        stream_id="stream_cam_123",
        event="stream_started",
        status="running",
        protocol="webrtc",
        message="Stream is running.",
        playback_url="http://localhost:8889/cam_123/whep",
        playlist_path="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        desired_state="running",
        timestamp=datetime.now(timezone.utc),
    )

    await repository.apply_event(event)

    assert database.calls
    _, params = database.calls[0]
    assert params[2] == "running"
    assert params[3] == "running"
    assert params[4] == "webrtc"
