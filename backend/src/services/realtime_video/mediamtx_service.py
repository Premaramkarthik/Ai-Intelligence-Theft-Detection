"""Managed MediaMTX lifecycle and dynamic path configuration."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
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
from src.services.realtime_video.mediamtx_control_api import (
    MediaMtxControlApiClient,
    MediaMtxControlApiException,
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
        self._control_api_username = settings.mediamtx_api_username
        self._control_api_password = _resolve_control_api_password(settings)
        self._control_api = MediaMtxControlApiClient(
            settings.mediamtx_api_base_url,
            settings.mediamtx_api_timeout_seconds,
            self._control_api_username,
            self._control_api_password,
        )
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
                    await self._ensure_runtime_path_present(camera)
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

    async def sync_config(
        self,
        cameras: list[CameraRecord],
        *,
        strict_runtime_sync: bool = True,
    ) -> None:
        """Write the generated MediaMTX config without starting or stopping any process."""

        async with self._lock:
            await self._sync_config_unlocked(
                cameras,
                strict_runtime_sync=strict_runtime_sync,
            )

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
        config_path.write_text(config_text, encoding="utf-8")
        self._logger.info("Wrote generated MediaMTX config to %s.", config_path)

    async def _sync_config_unlocked(
        self,
        cameras: list[CameraRecord],
        *,
        strict_runtime_sync: bool = True,
    ) -> None:
        """Refresh the generated MediaMTX config when the camera inventory changes."""

        config_text = self._render_config(cameras)
        config_hash = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
        if config_hash == self._config_hash:
            if not self._settings.mediamtx_manage_process:
                await self._sync_runtime_paths_with_policy_unlocked(
                    cameras,
                    strict_runtime_sync=strict_runtime_sync,
                )
            return
        await self._write_config(config_text)
        self._config_hash = config_hash
        self._logger.info(
            "Generated MediaMTX config for %s camera path(s).",
            len(cameras),
        )
        if not self._settings.mediamtx_manage_process:
            await self._sync_runtime_paths_with_policy_unlocked(
                cameras,
                strict_runtime_sync=strict_runtime_sync,
            )

    async def _sync_runtime_paths_with_policy_unlocked(
        self,
        cameras: list[CameraRecord],
        *,
        strict_runtime_sync: bool,
    ) -> None:
        """Synchronize runtime paths or degrade gracefully when startup is non-strict."""

        try:
            await self._sync_runtime_paths_unlocked(cameras)
        except MediaMtxStartupException:
            if strict_runtime_sync:
                raise
            self._logger.warning(
                "MediaMTX runtime path synchronization is unavailable during startup; "
                "the backend will continue in degraded mode until MediaMTX becomes ready.",
            )
            return

        self._logger.info(
            "MediaMTX runtime paths are synchronized through the Control API at %s.",
            self._settings.mediamtx_api_base_url,
        )

    async def _sync_runtime_paths_unlocked(self, cameras: list[CameraRecord]) -> None:
        """Reconcile runtime MediaMTX paths through the Control API in external-service mode."""

        desired_paths = _render_runtime_path_configs(cameras)
        try:
            configured_paths = await self._call_control_api_with_retry(
                self._control_api.list_configured_paths,
                operation_name="list MediaMTX runtime paths",
            )
            for path_name, payload in desired_paths.items():
                await self._call_control_api_with_retry(
                    lambda path_name=path_name, payload=payload: self._control_api.upsert_path(
                        path_name,
                        payload,
                        configured_paths,
                    ),
                    operation_name=f"upsert MediaMTX path '{path_name}'",
                )
            stale_paths = sorted(
                set(configured_paths) - set(desired_paths) - {"all_others"},
            )
            for path_name in stale_paths:
                await self._call_control_api_with_retry(
                    lambda path_name=path_name: self._control_api.delete_path(path_name),
                    operation_name=f"delete MediaMTX path '{path_name}'",
                )
        except MediaMtxControlApiException as exc:
            self._last_error = str(exc)
            raise MediaMtxStartupException(
                "MediaMTX runtime path synchronization failed through the Control API.",
                details={
                    "api_base_url": self._settings.mediamtx_api_base_url,
                    "error": str(exc),
                },
            ) from exc

        self._last_error = None
        self._logger.info(
            "Reconciled %s MediaMTX runtime path(s) through the Control API.",
            len(desired_paths),
        )

    async def _ensure_runtime_path_present(self, camera: CameraRecord) -> None:
        """Verify that the requested camera path exists in MediaMTX runtime configuration."""

        path_name = stream_name_from_camera(camera)
        try:
            path_exists = await self._call_control_api_with_retry(
                lambda: self._control_api.path_exists(path_name),
                operation_name=f"verify MediaMTX path '{path_name}'",
            )
        except MediaMtxControlApiException as exc:
            self._last_error = str(exc)
            raise MediaMtxStartupException(
                "MediaMTX runtime path verification failed through the Control API.",
                details={
                    "api_base_url": self._settings.mediamtx_api_base_url,
                    "stream_name": path_name,
                    "error": str(exc),
                },
            ) from exc

        if path_exists:
            return

        self._last_error = f"MediaMTX path '{path_name}' is not loaded."
        raise MediaMtxStartupException(
            "MediaMTX has not loaded the requested camera path yet.",
            details={
                "api_base_url": self._settings.mediamtx_api_base_url,
                "stream_name": path_name,
            },
        )

    async def _call_control_api_with_retry(
        self,
        operation: Callable[[], Awaitable[Any]],
        *,
        operation_name: str,
    ) -> Any:
        """Retry transient MediaMTX Control API failures while config changes propagate."""

        deadline = (
            asyncio.get_running_loop().time()
            + self._settings.mediamtx_api_ready_timeout_seconds
        )
        while True:
            try:
                return await operation()
            except MediaMtxControlApiException as exc:
                if (
                    not _is_retryable_control_api_exception(exc)
                    or asyncio.get_running_loop().time() >= deadline
                ):
                    raise
                self._logger.warning(
                    "MediaMTX Control API operation '%s' is not ready yet: %s",
                    operation_name,
                    exc,
                )
                await asyncio.sleep(0.25)

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
                "authMethod: internal",
                "authInternalUsers:",
                "  - user: any",
                "    pass:",
                "    ips: []",
                "    permissions:",
                "      - action: publish",
                "        path:",
                "      - action: read",
                "        path:",
                "      - action: playback",
                "        path:",
                "  - user: any",
                "    pass:",
                "    ips: ['127.0.0.1', '::1']",
                "    permissions:",
                "      - action: api",
                "      - action: metrics",
                "      - action: pprof",
                f"  - user: {_yaml_scalar(self._control_api_username)}",
                f"    pass: {_yaml_scalar(self._control_api_password)}",
                "    ips: []",
                "    permissions:",
                "      - action: api",
                "      - action: metrics",
                "      - action: pprof",
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


def _render_runtime_path_configs(cameras: list[CameraRecord]) -> dict[str, dict[str, Any]]:
    """Render the runtime path payloads used by the MediaMTX Control API."""

    runtime_paths: dict[str, dict[str, Any]] = {}
    for camera in cameras:
        try:
            source_url = build_rtsp_url_from_camera(camera)
        except ValueError:
            continue
        runtime_paths[stream_name_from_camera(camera)] = {
            "source": source_url,
            "sourceOnDemand": True,
            "sourceOnDemandStartTimeout": "10s",
            "sourceOnDemandCloseAfter": "15s",
            "rtspTransport": "tcp",
            "useAbsoluteTimestamp": False,
            "overridePublisher": False,
        }
    return runtime_paths


def stream_name_from_camera(camera: CameraRecord) -> str:
    """Return the MediaMTX path name that should be used for a camera."""

    metadata_name = camera.metadata.get("mediamtx_stream_name")
    if isinstance(metadata_name, str) and metadata_name.strip():
        return normalize_stream_name(metadata_name)
    return normalize_stream_name(camera.id)


def _is_retryable_control_api_exception(exc: MediaMtxControlApiException) -> bool:
    """Return whether a MediaMTX Control API error is worth retrying."""

    if exc.status_code == 401:
        return True
    if exc.status_code is not None and exc.status_code >= 500:
        return True
    return exc.reason is not None


def _yaml_scalar(value: str) -> str:
    """Render a safe scalar value that is valid in both YAML and JSON syntaxes."""

    return json.dumps(value)


def _resolve_control_api_password(settings: Settings) -> str:
    """Load or create the MediaMTX Control API password shared with the generated config."""

    if settings.mediamtx_api_password is not None:
        return settings.mediamtx_api_password.get_secret_value()

    password_file = settings.mediamtx_api_password_file
    password_file.parent.mkdir(parents=True, exist_ok=True)
    if password_file.exists():
        existing_password = password_file.read_text(encoding="utf-8").strip()
        if existing_password:
            return existing_password

    generated_password = secrets.token_urlsafe(24)
    password_file.write_text(generated_password, encoding="utf-8")
    return generated_password
