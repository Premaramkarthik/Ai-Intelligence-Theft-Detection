from dataclasses import dataclass

import pytest
from fastapi import HTTPException, WebSocket

from services.signaling.api.deps import verify_ws_token
from services.signaling.api.routes.events import get_recent_events
from services.signaling.services.camera_service import build_stream_message


class FakePool:
    async def fetch(self, _query: str, _limit: int):
        return [
            {
                "event_id": "evt-1",
                "camera_id": "cam-1",
                "trace_id": "trace-1",
                "event_type": "shoplifting.detected",
                "class_name": "shoplifting",
                "confidence": 0.91,
                "severity": "high",
                "created_at": __import__("datetime").datetime.fromisoformat("2026-03-13T12:00:00+00:00"),
                "detections": [],
                "metadata": {"source": "unit-test"},
            }
        ]

    async def fetchval(self, _query: str):
        return 1


@dataclass
class FakeDB:
    pool: FakePool

    def get_pool(self):
        return self.pool


@dataclass
class FakeApp:
    state: object


@dataclass
class FakeState:
    db: FakeDB


@dataclass
class FakeRequest:
    app: FakeApp


class FakeWebSocket:
    def __init__(self, query_params: dict[str, str] | None = None, headers: dict[str, str] | None = None):
        self.query_params = query_params or {}
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_history_route_returns_canonical_fields():
    request = FakeRequest(app=FakeApp(state=FakeState(db=FakeDB(pool=FakePool()))))

    payload = await get_recent_events(request=request, limit=10, _user="tester")

    assert payload[0]["event_id"] == "evt-1"
    assert payload[0]["timestamp"] == "2026-03-13T12:00:00+00:00"
    assert payload[0]["severity"] == "high"


def test_stream_message_builder_matches_frontend_protocol():
    payload = build_stream_message(
        camera_id="cam-1",
        jpeg=b"fake-image",
        metadata={
            "timestamp": "2026-03-13T12:00:00+00:00",
            "detections": [],
            "incident": None,
        },
    )

    assert payload["message_type"] == "camera.stream"
    assert payload["camera_id"] == "cam-1"
    assert payload["image_jpeg_base64"]


def test_verify_ws_token_rejects_missing_token():
    with pytest.raises(HTTPException):
        verify_ws_token(FakeWebSocket())  # type: ignore[arg-type]
