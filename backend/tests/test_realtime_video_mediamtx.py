"""Tests for MediaMTX connectivity helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from src.services.realtime_video.mediamtx import (
    is_rtsp_endpoint_reachable,
    parse_rtsp_endpoint,
)


def test_parse_rtsp_endpoint_uses_default_rtsp_port() -> None:
    """Default MediaMTX RTSP URLs to port 8554 when the port is omitted."""

    host, port = parse_rtsp_endpoint("rtsp://localhost/front_gate")

    assert host == "localhost"
    assert port == 8554


@pytest.mark.asyncio
async def test_is_rtsp_endpoint_reachable_detects_open_port(monkeypatch) -> None:
    """Report reachable when the TCP dial to MediaMTX succeeds."""

    writer = Mock()
    writer.wait_closed = AsyncMock()
    monkeypatch.setattr(
        "src.services.realtime_video.mediamtx.asyncio.open_connection",
        AsyncMock(return_value=(object(), writer)),
    )

    assert await is_rtsp_endpoint_reachable("rtsp://127.0.0.1:8554/camera")
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_rtsp_endpoint_reachable_detects_closed_port() -> None:
    """Report unreachable when the TCP listener is absent."""

    assert not await is_rtsp_endpoint_reachable(
        "rtsp://127.0.0.1:6553/camera",
        timeout_seconds=0.1,
    )
