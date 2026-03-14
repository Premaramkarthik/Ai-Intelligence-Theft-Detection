from shared.types.events import (
    CameraStreamMessage,
    DetectionPayload,
    FrameReference,
    FrameTelemetryMessage,
    IncidentEvent,
    IncidentPayload,
    Severity,
)


def test_canonical_telemetry_schema_round_trip():
    message = FrameTelemetryMessage(
        camera_id="cam-1",
        trace_id="trace-1",
        timestamp="2026-03-13T12:00:00+00:00",
        capture_timestamp=123.4,
        detections=[DetectionPayload(bbox=[1, 2, 3, 4], label="person", confidence=0.9, track_id="7")],
        incident=IncidentPayload(label="shoplifting", confidence=0.97, severity=Severity.CRITICAL),
        frame_ref=FrameReference(camera_id="cam-1", slot_id=4, generation=2),
        metadata={"config_version": 5},
    )

    payload = message.model_dump(mode="json")

    assert payload["message_type"] == "telemetry.frame"
    assert payload["timestamp"] == "2026-03-13T12:00:00+00:00"
    assert payload["incident"]["severity"] == "critical"
    assert payload["frame_ref"]["generation"] == 2


def test_incident_event_contract_contains_history_fields():
    event = IncidentEvent(
        camera_id="cam-2",
        trace_id="trace-2",
        timestamp="2026-03-13T12:01:00+00:00",
        label="shoplifting",
        confidence=0.92,
        severity=Severity.HIGH,
        detections=[],
        frame_ref=FrameReference(camera_id="cam-2", slot_id=9, generation=4),
        metadata={"model": "efficient_x3d"},
    )

    payload = event.model_dump(mode="json")

    assert payload["message_type"] == "incident.event"
    assert payload["event_id"]
    assert payload["event_type"] == "shoplifting.detected"
    assert payload["severity"] == "high"


def test_camera_stream_contract_uses_single_json_message():
    message = CameraStreamMessage(
        camera_id="cam-3",
        timestamp="2026-03-13T12:02:00+00:00",
        image_jpeg_base64="ZmFrZQ==",
        detections=[],
        incident=None,
    )

    payload = message.model_dump(mode="json")

    assert payload["message_type"] == "camera.stream"
    assert payload["image_jpeg_base64"] == "ZmFrZQ=="
