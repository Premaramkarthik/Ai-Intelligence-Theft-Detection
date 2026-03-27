"""Managed MediaMTX lifecycle and dynamic path configuration."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlparse

from src.core.config import Settings
from src.core.exceptions.stream.stream_exceptions import (
    MediaMtxStartupException,
    MediaMtxUnavailableException,
)
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord
from src.services.realtime_video.mediamtx import (
    build_stream_endpoints,
    is_rtsp_endpoint_reachable,
    normalize_stream_name,
)
from src.utils.ffmpeg import build_rtsp_url_from_camera


@dataclass(slots=True)
class MediaMtxHealthSnapshot:
    """Summarize the current MediaMTX lifecycle state."""

    healthy: bool
    managed: bool
    externally_managed: bool
    config_path: str
    last_error: str | None = None


class MediaMtxService:
    """Own MediaMTX startup and dynamic path configuration for camera streams."""

    def __init__(self, settings: Settings) -> None:
        """Create a MediaMTX orchestration service for the current backend settings."""

        self._settings = settings
        self._logger = get_logger(__name__)
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._config_hash: str | None = None
        self._last_error: str | None = None
        self._externally_managed = False
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    async def ensure_ready(self, cameras: list[CameraRecord], camera: CameraRecord) -> None:
        """Ensure MediaMTX is running and configured for the requested camera path."""

        async with self._lock:
            await self._sync_config_unlocked(cameras)
            if await self._is_rtsp_listener_ready():
                self._externally_managed = self._process is None
                if self._externally_managed:
                    self._logger.info(
                        "Using externally managed MediaMTX listener at %s.",
                        self._settings.mediamtx_rtsp_base_url,
                    )
                return

            if not self._settings.mediamtx_manage_process:
                raise MediaMtxUnavailableException(
                    camera.id,
                    build_stream_endpoints(
                        stream_name_from_camera(camera),
                        rtsp_base_url=self._settings.mediamtx_rtsp_base_url,
                        hls_base_url=self._settings.mediamtx_hls_base_url,
                        whep_base_url=self._settings.mediamtx_webrtc_base_url,
                    ).rtsp_pull_url,
                    details={"stream_name": stream_name_from_camera(camera)},
                )

            config_text = self._render_config(cameras)
            config_hash = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
            config_changed = config_hash != self._config_hash
            if config_changed or not self._is_managed_process_alive():
                await self._write_config(config_text)
                await self._restart_process()
                self._config_hash = config_hash
            await self._wait_until_ready(camera)

    async def sync_config(self, cameras: list[CameraRecord]) -> None:
        """Write the generated MediaMTX config without starting or stopping any process."""

        async with self._lock:
            await self._sync_config_unlocked(cameras)

    async def stop(self) -> None:
        """Stop the managed MediaMTX process if the backend started it."""

        async with self._lock:
            await self._stop_process()

    def health_snapshot(self) -> MediaMtxHealthSnapshot:
        """Return a health snapshot for API and diagnostics endpoints."""

        return MediaMtxHealthSnapshot(
            healthy=self._externally_managed or self._is_managed_process_alive(),
            managed=self._settings.mediamtx_manage_process,
            externally_managed=self._externally_managed,
            config_path=str(self._settings.mediamtx_generated_config_path),
            last_error=self._last_error,
        )

    async def _restart_process(self) -> None:
        """Restart the managed MediaMTX process with the latest generated config."""

        await self._stop_process()
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._settings.mediamtx_binary,
                str(self._settings.mediamtx_generated_config_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise MediaMtxStartupException(
                "The MediaMTX binary was not found in PATH.",
                details={"binary": self._settings.mediamtx_binary},
            ) from exc

        self._externally_managed = False
        if self._process.stdout is not None:
            self._stdout_task = asyncio.create_task(
                self._log_stream(self._process.stdout, "stdout"),
            )
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(
                self._log_stream(self._process.stderr, "stderr"),
            )
        self._logger.info(
            "Started managed MediaMTX with config %s.",
            self._settings.mediamtx_generated_config_path,
        )

    async def _stop_process(self) -> None:
        """Terminate the managed MediaMTX process and its log forwarders."""

        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._process.wait(), timeout=5)
            if self._process.returncode is None:
                self._process.kill()
                await self._process.wait()
        self._process = None
        await self._cancel_log_tasks()

    async def _cancel_log_tasks(self) -> None:
        """Cancel background log tasks created for the managed MediaMTX process."""

        for task in (self._stdout_task, self._stderr_task):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._stdout_task = None
        self._stderr_task = None

    async def _log_stream(
        self,
        stream: asyncio.StreamReader,
        stream_name: str,
    ) -> None:
        """Forward MediaMTX process output into the backend logger."""

        while True:
            line = await stream.readline()
            if not line:
                return
            self._logger.info("MediaMTX %s: %s", stream_name, line.decode("utf-8").rstrip())

    async def _write_config(self, config_text: str) -> None:
        """Persist the generated MediaMTX config to disk for process startup."""

        config_path = self._settings.mediamtx_generated_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(config_path.write_text, config_text, "utf-8")
        self._logger.info("Wrote generated MediaMTX config to %s.", config_path)

    async def _sync_config_unlocked(self, cameras: list[CameraRecord]) -> None:
        """Refresh the generated MediaMTX config when the camera inventory changes."""

        config_text = self._render_config(cameras)
        config_hash = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
        if config_hash == self._config_hash:
            return
        await self._write_config(config_text)
        self._config_hash = config_hash
        self._logger.info(
            "Generated MediaMTX config for %s camera path(s).",
            len(cameras),
        )
        if not self._settings.mediamtx_manage_process:
            self._logger.warning(
                "MediaMTX config changed in external-service mode. Reload or restart "
                "the external MediaMTX instance to apply %s.",
                self._settings.mediamtx_generated_config_path,
            )

    async def _wait_until_ready(self, camera: CameraRecord) -> None:
        """Wait for the managed MediaMTX RTSP listener to become reachable."""

        deadline = asyncio.get_running_loop().time() + self._settings.mediamtx_start_timeout_seconds
        rtsp_url = build_stream_endpoints(
            stream_name_from_camera(camera),
            rtsp_base_url=self._settings.mediamtx_rtsp_base_url,
            hls_base_url=self._settings.mediamtx_hls_base_url,
            whep_base_url=self._settings.mediamtx_webrtc_base_url,
        ).rtsp_pull_url
        while asyncio.get_running_loop().time() < deadline:
            if await is_rtsp_endpoint_reachable(rtsp_url):
                self._last_error = None
                return
            await asyncio.sleep(0.25)
        self._last_error = "MediaMTX listener did not become reachable before timeout."
        raise MediaMtxStartupException(
            "Managed MediaMTX did not become ready before the startup timeout elapsed.",
            details={"rtsp_url": rtsp_url},
        )

    async def _is_rtsp_listener_ready(self) -> bool:
        """Return whether the configured MediaMTX RTSP listener accepts connections."""

        return await is_rtsp_endpoint_reachable(self._settings.mediamtx_rtsp_base_url)

    def _is_managed_process_alive(self) -> bool:
        """Return whether the managed MediaMTX process is still running."""

        return self._process is not None and self._process.returncode is None

    def _render_config(self, cameras: list[CameraRecord]) -> str:
        """Render a complete MediaMTX config containing all known camera paths."""

        rtsp_port = _port_from_url(self._settings.mediamtx_rtsp_base_url, 8554)
        hls_port = _port_from_url(self._settings.mediamtx_hls_base_url, 8888)
        webrtc_port = _port_from_url(self._settings.mediamtx_webrtc_base_url, 8889)
        webrtc_hosts = _webrtc_hosts(self._settings.mediamtx_webrtc_base_url)
        path_lines = _render_path_lines(cameras)
        return "\n".join(
            [
                "logLevel: info",
                "logDestinations: [stdout]",
                "logStructured: false",
                "",
                "readTimeout: 10s",
                "writeTimeout: 10s",
                "writeQueueSize: 1024",
                "",
                "api: true",
                "apiAddress: :9997",
                "metrics: true",
                "metricsAddress: :9998",
                "",
                "rtsp: true",
                f"rtspAddress: :{rtsp_port}",
                "rtspTransports: [tcp]",
                "",
                "hls: true",
                f"hlsAddress: :{hls_port}",
                "hlsAlwaysRemux: true",
                "hlsVariant: lowLatency",
                "hlsSegmentCount: 7",
                "hlsSegmentDuration: 1s",
                "hlsPartDuration: 200ms",
                "hlsMuxerCloseAfter: 30s",
                "",
                "webrtc: true",
                f"webrtcAddress: :{webrtc_port}",
                "webrtcAllowOrigins: ['*']",
                "webrtcLocalUDPAddress: :8189",
                "webrtcLocalTCPAddress: ''",
                "webrtcIPsFromInterfaces: true",
                "webrtcIPsFromInterfacesList: []",
                "webrtcAdditionalHosts:",
                *[f"  - {host}" for host in webrtc_hosts],
                "webrtcSTUNGatherTimeout: 5s",
                "webrtcHandshakeTimeout: 10s",
                "webrtcTrackGatherTimeout: 2s",
                "",
                "pathDefaults:",
                "  sourceOnDemand: true",
                "  sourceOnDemandStartTimeout: 10s",
                "  sourceOnDemandCloseAfter: 15s",
                "  useAbsoluteTimestamp: false",
                "  rtspTransport: tcp",
                "  overridePublisher: false",
                "",
                "paths:",
                *path_lines,
                "",
            ],
        )

def _port_from_url(url: str, default_port: int) -> int:
    """Extract a port from a URL and fall back to the protocol default when omitted."""

    parsed = urlparse(url)
    return parsed.port or default_port


def _webrtc_hosts(base_url: str) -> list[str]:
    """Build the list of hostnames that MediaMTX should advertise for WebRTC."""

    parsed = urlparse(base_url)
    hosts = ["localhost", "127.0.0.1"]
    if parsed.hostname and parsed.hostname not in hosts:
        hosts.append(parsed.hostname)
    return hosts


def _render_path_lines(cameras: list[CameraRecord]) -> list[str]:
    """Render the per-camera MediaMTX path definitions for the generated config."""

    if not cameras:
        return ["  {}"]

    lines: list[str] = []
    for camera in cameras:
        try:
            source_url = build_rtsp_url_from_camera(camera)
        except ValueError:
            continue
        stream_name = stream_name_from_camera(camera)
        lines.append(f"  {stream_name}:")
        lines.append(f"    source: {json.dumps(source_url)}")
    return lines


def stream_name_from_camera(camera: CameraRecord) -> str:
    """Return the MediaMTX path name that should be used for a camera."""

    metadata_name = camera.metadata.get("mediamtx_stream_name")
    if isinstance(metadata_name, str) and metadata_name.strip():
        return normalize_stream_name(metadata_name)
    return normalize_stream_name(camera.id)
