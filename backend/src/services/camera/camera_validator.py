from __future__ import annotations

import asyncio
import importlib
import json
import subprocess
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
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout + 2,
            )
        except FileNotFoundError:
            self._logger.warning(
                "ffprobe is not available in PATH. Falling back to PyAV RTSP validation.",
            )
            return await asyncio.to_thread(
                self._validate_with_pyav,
                camera,
                rtsp_url,
                timeout,
                started,
            )
        except PermissionError:
            self._logger.warning(
                "ffprobe subprocess could not be started on this Windows host. "
                "Falling back to PyAV RTSP validation.",
            )
            return await asyncio.to_thread(
                self._validate_with_pyav,
                camera,
                rtsp_url,
                timeout,
                started,
            )
        except subprocess.TimeoutExpired:
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
        stdout = completed.stdout
        stderr = completed.stderr
        stderr_text = stderr.decode("utf-8", errors="ignore").strip()

        if completed.returncode == 0:
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

    def _validate_with_pyav(
        self,
        camera: CameraRecord,
        rtsp_url: str,
        timeout: int,
        started: float,
    ) -> CameraValidationResult:
        try:
            av_module = importlib.import_module("av")
            container = av_module.open(
                rtsp_url,
                mode="r",
                timeout=(timeout, timeout),
                options={
                    "rtsp_transport": camera.transport.value,
                    "fflags": "nobuffer",
                    "flags": "low_delay",
                    "reorder_queue_size": "0",
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            code, message = self._map_probe_error(str(exc))
            self._logger.warning(
                "PyAV RTSP validation failed for camera %s: %s",
                camera.id,
                exc,
            )
            return CameraValidationResult(
                is_reachable=False,
                code=code,
                message=message,
                resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
                latency_ms=int((time.perf_counter() - started) * 1000),
                details={"stderr": str(exc), "validator": "pyav"},
                validated_at=datetime.now(timezone.utc),
            )

        try:
            video_stream = container.streams.video[0]
            codec_context = getattr(video_stream, "codec_context", None)
            return CameraValidationResult(
                is_reachable=True,
                code="RTSP_REACHABLE",
                message="RTSP endpoint responded successfully.",
                resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
                latency_ms=int((time.perf_counter() - started) * 1000),
                details={
                    "streams": [
                        {
                            "index": getattr(video_stream, "index", None),
                            "codec_name": getattr(codec_context, "name", None),
                            "codec_type": getattr(video_stream, "type", None),
                            "width": getattr(codec_context, "width", None),
                            "height": getattr(codec_context, "height", None),
                        },
                    ],
                    "validator": "pyav",
                },
                validated_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # pylint: disable=broad-except
            code, message = self._map_probe_error(str(exc))
            self._logger.warning(
                "PyAV RTSP validation did not find a usable video stream for camera %s: %s",
                camera.id,
                exc,
            )
            return CameraValidationResult(
                is_reachable=False,
                code=code,
                message=message,
                resolved_rtsp_url_preview=mask_rtsp_url(rtsp_url),
                latency_ms=int((time.perf_counter() - started) * 1000),
                details={"stderr": str(exc), "validator": "pyav"},
                validated_at=datetime.now(timezone.utc),
            )
        finally:
            container.close()
