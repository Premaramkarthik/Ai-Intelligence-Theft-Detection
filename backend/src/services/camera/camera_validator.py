from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.core.config import Settings
from src.core.exceptions.camera.camera_exceptions import CameraValidationException
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord
from src.utils.ffmpeg import build_rtsp_url_from_camera, mask_rtsp_url


@dataclass(slots=True)
class CameraValidationResult:
    is_reachable: bool
    code: str
    message: str
    resolved_rtsp_url_preview: str
    latency_ms: int | None
    details: dict[str, Any] | None
    validated_at: datetime


class CameraValidator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(__name__)

    async def validate(
        self,
        camera: CameraRecord,
        timeout_seconds: int | None = None,
    ) -> CameraValidationResult:
        try:
            rtsp_url = build_rtsp_url_from_camera(camera)
        except ValueError as exc:
            raise CameraValidationException(str(exc), "INVALID_RTSP_CONFIGURATION") from exc

        timeout = timeout_seconds or self._settings.validation_timeout_seconds
        started = time.perf_counter()
        command = [
            self._settings.ffprobe_binary,
            "-v",
            "error",
            "-rtsp_transport",
            camera.transport.value,
            "-rw_timeout",
            str(timeout * 1_000_000),
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=index,codec_name,codec_type,width,height",
            "-of",
            "json",
            rtsp_url,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CameraValidationException(
                "ffprobe is not installed or not available in PATH.",
                "FFPROBE_NOT_AVAILABLE",
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout + 2)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return CameraValidationResult(
                is_reachable=False,
                code="RTSP_TIMEOUT",
                message="Timed out while validating the RTSP endpoint.",
                resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
                latency_ms=int((time.perf_counter() - started) * 1000),
                details=None,
                validated_at=datetime.now(timezone.utc),
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        stderr_text = stderr.decode("utf-8", errors="ignore").strip()

        if process.returncode == 0:
            probe_payload = json.loads(stdout.decode("utf-8") or "{}")
            return CameraValidationResult(
                is_reachable=True,
                code="RTSP_REACHABLE",
                message="RTSP endpoint responded successfully.",
                resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
                latency_ms=latency_ms,
                details=probe_payload,
                validated_at=datetime.now(timezone.utc),
            )

        code, message = self._map_probe_error(stderr_text)
        self._logger.warning("RTSP validation failed for camera %s: %s", camera.id, stderr_text)
        return CameraValidationResult(
            is_reachable=False,
            code=code,
            message=message,
            resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
            latency_ms=latency_ms,
            details={"stderr": stderr_text} if stderr_text else None,
            validated_at=datetime.now(timezone.utc),
        )

    def _map_probe_error(self, stderr_text: str) -> tuple[str, str]:
        normalized = stderr_text.lower()
        if "401" in normalized or "unauthorized" in normalized or "authentication" in normalized:
            return "RTSP_AUTH_FAILED", "Camera credentials were rejected by the RTSP server."
        if "timed out" in normalized or "timeout" in normalized:
            return "RTSP_TIMEOUT", "Timed out while reaching the RTSP server."
        if "no route to host" in normalized or "network is unreachable" in normalized:
            return "RTSP_HOST_UNREACHABLE", "The RTSP host could not be reached from the backend."
        return "RTSP_UNREACHABLE", "The RTSP endpoint could not be validated."
