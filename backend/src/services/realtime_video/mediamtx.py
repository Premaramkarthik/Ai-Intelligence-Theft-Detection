"""Helpers for addressing streams exposed by MediaMTX."""

from __future__ import annotations

import asyncio
import re
from asyncio import TimeoutError as AsyncTimeoutError
from urllib.parse import urlparse

from src.services.realtime_video.contracts import MediaMtxStreamEndpoints

_STREAM_NAME_SANITIZER = re.compile(r"[^a-zA-Z0-9_-]+")


def build_rtsp_pull_url(base_url: str, stream_name: str) -> str:
    """Build the internal RTSP pull URL used by PyAV workers."""

    return f"{base_url.rstrip('/')}/{stream_name}"


def build_hls_url(base_url: str, stream_name: str) -> str:
    """Build the low-latency HLS playback URL exposed by MediaMTX."""

    normalized = base_url.rstrip("/")
    return f"{normalized}/{stream_name}/index.m3u8"


def build_whep_url(base_url: str, stream_name: str) -> str:
    """Build the WHEP endpoint consumed by WebRTC clients."""

    normalized = base_url.rstrip("/")
    return f"{normalized}/{stream_name}/whep"


def build_stream_endpoints(
    stream_name: str,
    *,
    rtsp_base_url: str = "rtsp://localhost:8554",
    hls_base_url: str = "http://localhost:8888",
    whep_base_url: str = "http://localhost:8889",
) -> MediaMtxStreamEndpoints:
    """Build all MediaMTX endpoints associated with a logical stream."""

    return MediaMtxStreamEndpoints(
        stream_name=stream_name,
        rtsp_pull_url=build_rtsp_pull_url(rtsp_base_url, stream_name),
        hls_url=build_hls_url(hls_base_url, stream_name),
        whep_url=build_whep_url(whep_base_url, stream_name),
    )


def normalize_stream_name(raw_name: str) -> str:
    """Normalize arbitrary camera identifiers into stable MediaMTX path names."""

    normalized = _STREAM_NAME_SANITIZER.sub("_", raw_name).strip("_")
    return normalized or "camera_stream"


def parse_rtsp_endpoint(rtsp_url: str) -> tuple[str, int]:
    """Extract the hostname and port from a MediaMTX RTSP URL."""

    parsed = urlparse(rtsp_url)
    if parsed.hostname is None:
        raise ValueError(f"RTSP URL '{rtsp_url}' does not include a hostname.")
    return parsed.hostname, parsed.port or 8554


async def is_rtsp_endpoint_reachable(
    rtsp_url: str,
    timeout_seconds: float = 1.5,
) -> bool:
    """Return whether a MediaMTX RTSP endpoint accepts TCP connections."""

    host, port = parse_rtsp_endpoint(rtsp_url)
    try:
        connection = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_seconds,
        )
    except (
        AsyncTimeoutError,
        ConnectionError,
        OSError,
    ):
        return False

    reader, writer = connection
    del reader
    writer.close()
    await writer.wait_closed()
    return True
