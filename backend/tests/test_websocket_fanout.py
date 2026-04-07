"""Tests for WebSocketManager: broadcast-all, evict-slow-clients, camera_id filter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from src.schemas.common import WebSocketEnvelope
from src.services.presentation.websocket_manager import WebSocketManager


def _make_ws() -> AsyncMock:
    ws = AsyncMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    return ws


def _envelope(camera_id: str | None = "cam1") -> WebSocketEnvelope:
    return WebSocketEnvelope(
        type="tracking",
        topic="tracks",
        message="update",
        camera_id=camera_id,
    )


# ---------------------------------------------------------------------------
# broadcast reaches all connected clients
# ---------------------------------------------------------------------------


async def test_broadcast_reaches_all_connected_clients() -> None:
    manager = WebSocketManager()
    ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()

    # All connected with no camera filter (camera_id=None → receive everything).
    await manager.connect(ws1, camera_id=None)
    await manager.connect(ws2, camera_id=None)
    await manager.connect(ws3, camera_id=None)

    await manager.broadcast(_envelope(camera_id="cam1"))

    ws1.send_json.assert_awaited_once()
    ws2.send_json.assert_awaited_once()
    ws3.send_json.assert_awaited_once()


# ---------------------------------------------------------------------------
# stale clients are evicted after send failure
# ---------------------------------------------------------------------------


async def test_client_that_raises_on_send_is_evicted() -> None:
    manager = WebSocketManager()
    good_ws = _make_ws()
    bad_ws = _make_ws()
    bad_ws.send_json.side_effect = Exception("connection closed")

    await manager.connect(good_ws, camera_id=None)
    await manager.connect(bad_ws, camera_id=None)

    await manager.broadcast(_envelope())

    # good_ws must still be registered.
    assert good_ws in manager._connections
    # bad_ws must have been evicted.
    assert bad_ws not in manager._connections


async def test_client_that_times_out_on_send_is_evicted() -> None:
    manager = WebSocketManager()
    slow_ws = _make_ws()

    async def _hang(*_args, **_kwargs):  # noqa: ANN001
        await asyncio.sleep(10)

    slow_ws.send_json.side_effect = _hang

    await manager.connect(slow_ws, camera_id=None)

    # broadcast applies a 2s timeout per client; patch it to 0.05s for speed.
    with patch("src.services.presentation.websocket_manager.asyncio.wait_for") as mock_wf:

        async def _timeout_immediately(coro, timeout):  # noqa: ANN001
            raise asyncio.TimeoutError

        mock_wf.side_effect = _timeout_immediately
        await manager.broadcast(_envelope())

    assert slow_ws not in manager._connections


# ---------------------------------------------------------------------------
# camera_id filter: only matching subscribers receive the message
# ---------------------------------------------------------------------------


async def test_camera_id_filter_delivers_only_to_matching_subscribers() -> None:
    manager = WebSocketManager()
    ws_all = _make_ws()       # camera_id=None → receives everything
    ws_cam1 = _make_ws()      # subscribed to cam1 only
    ws_cam2 = _make_ws()      # subscribed to cam2 only

    await manager.connect(ws_all, camera_id=None)
    await manager.connect(ws_cam1, camera_id="cam1")
    await manager.connect(ws_cam2, camera_id="cam2")

    await manager.broadcast(_envelope(camera_id="cam1"))

    ws_all.send_json.assert_awaited_once()
    ws_cam1.send_json.assert_awaited_once()
    assert ws_cam2.send_json.await_count == 0


# ---------------------------------------------------------------------------
# disconnect removes connection
# ---------------------------------------------------------------------------


async def test_disconnect_removes_websocket_from_registry() -> None:
    manager = WebSocketManager()
    ws = _make_ws()
    await manager.connect(ws, camera_id=None)
    assert ws in manager._connections

    await manager.disconnect(ws)
    assert ws not in manager._connections
