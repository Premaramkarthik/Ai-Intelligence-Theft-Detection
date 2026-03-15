from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis

from shared.core.config import CameraConfig
from shared.core.settings import get_settings
from shared.redis.keys import INCIDENT_STREAM_KEY, incident_channel, telemetry_channel, telemetry_latest_key
from shared.types.events import (
    CameraMetadataMessage,
    DetectionPayload,
    FrameReference,
    FrameTelemetryMessage,
    IncidentEvent,
    IncidentPayload,
    Severity,
    utc_now_iso,
)
from shared.types.models import FramePointer

STREAM_MAXLEN = 10000
_cfg = get_settings()


class TelemetryPublisher:
    async def publish(
        self,
        redis: aioredis.Redis,
        ptr: FramePointer,
        detections: list[DetectionPayload],
        incident: IncidentPayload | None,
        metadata: dict,
    ) -> None:
        telemetry = FrameTelemetryMessage(
            camera_id=ptr.camera_id,
            trace_id=ptr.trace_id,
            timestamp=utc_now_iso(),
            capture_timestamp=ptr.t_capture,
            detections=detections,
            incident=incident,
            frame_ref=FrameReference(
                camera_id=ptr.camera_id,
                slot_id=ptr.slot_id,
                generation=ptr.generation,
            ),
            metadata=metadata,
        )
        payload = telemetry.model_dump_json()
        await redis.publish(telemetry_channel(ptr.camera_id), payload)
        await redis.set(telemetry_latest_key(ptr.camera_id), payload)


class IncidentPublisher:
    async def publish(
        self,
        redis: aioredis.Redis,
        ptr: FramePointer,
        label: str,
        confidence: float,
        detections: list[DetectionPayload],
        config: CameraConfig,
        evidence: dict[str, Any],
    ) -> IncidentPayload:
        incident = IncidentPayload(
            label=label,
            confidence=float(confidence),
            severity=Severity.HIGH if confidence < 0.95 else Severity.CRITICAL,
        )
        event = IncidentEvent(
            camera_id=ptr.camera_id,
            organization_id=config.organization_id,
            store_id=config.store_id,
            trace_id=ptr.trace_id,
            timestamp=utc_now_iso(),
            label=label,
            confidence=float(confidence),
            severity=incident.severity,
            detections=detections,
            frame_ref=FrameReference(
                camera_id=ptr.camera_id,
                slot_id=ptr.slot_id,
                generation=ptr.generation,
            ),
            evidence_uri=evidence.get("evidence_uri"),
            thumbnail_uri=evidence.get("thumbnail_uri"),
            model_version=_cfg.model_version,
            config_version=str(int(config.loaded_at)),
            metadata={
                "t_capture": ptr.t_capture,
                "t_output": time.time(),
                "detector_model": "yolo26n.engine",
                "classifier_model": "cnn_transformer.engine",
                **evidence,
            },
        )
        payload = event.model_dump_json()
        await redis.xadd(INCIDENT_STREAM_KEY, {"payload": payload}, maxlen=STREAM_MAXLEN)
        await redis.publish(incident_channel(ptr.camera_id), payload)
        return incident


def build_camera_metadata_message(camera_id: str, metadata: dict) -> dict:
    message = CameraMetadataMessage(
        camera_id=camera_id,
        trace_id=metadata.get("trace_id"),
        timestamp=metadata.get("timestamp"),
        detections=metadata.get("detections", []),
        incident=metadata.get("incident"),
        review_status=metadata.get("review_status", "unreviewed"),
        metadata=metadata.get("metadata", {}),
    )
    return message.model_dump(mode="json")
