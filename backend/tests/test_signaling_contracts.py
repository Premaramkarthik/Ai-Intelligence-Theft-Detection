from dataclasses import dataclass

import pytest
from fastapi import HTTPException, WebSocket

from services.signaling.api.deps import verify_ws_token
from services.signaling.api.routes.events import ReviewUpdateRequest, get_recent_events, update_review
from services.signaling.services.camera_service import build_stream_message


class FakePool:
    async def fetch(self, _query: str, *args):
        return [
            {
                "event_id": "evt-1",
                "organization_id": "default-org",
                "store_id": "main-store",
                "camera_id": "cam-1",
                "trace_id": "trace-1",
                "event_type": "shoplifting.detected",
                "class_name": "shoplifting",
                "confidence": 0.91,
                "severity": "high",
                "review_status": "unreviewed",
                "review_note": None,
                "evidence_uri": "/data/evidence/trace-1.jpg",
                "thumbnail_uri": "/data/evidence/trace-1.thumb.jpg",
                "model_version": "yolo26n.engine+cnn_transformer.engine",
                "config_version": "1",
                "created_at": __import__("datetime").datetime.fromisoformat("2026-03-13T12:00:00+00:00"),
                "detections": [],
                "metadata": {"source": "unit-test"},
            }
        ]

    async def fetchval(self, _query: str):
        return 1

    async def execute(self, _query: str, *_args):
        return "UPDATE 1"


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

    assert payload[0].event_id == "evt-1"
    assert payload[0].timestamp == "2026-03-13T12:00:00+00:00"
    assert payload[0].severity == "high"
    assert payload[0].store_id == "main-store"


@pytest.mark.asyncio
async def test_review_update_route_accepts_status_change():
    request = FakeRequest(app=FakeApp(state=FakeState(db=FakeDB(pool=FakePool()))))

    payload = await update_review(
        event_id="evt-1",
        body=ReviewUpdateRequest(review_status="confirmed"),
        request=request,
        _user="tester",
    )

    assert payload["review_status"] == "confirmed"


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

    assert payload["message_type"] == "camera.metadata"
    assert payload["camera_id"] == "cam-1"
    assert payload["detections"] == []


def test_verify_ws_token_rejects_missing_token():
    with pytest.raises(HTTPException):
        verify_ws_token(FakeWebSocket())  # type: ignore[arg-type]
