from datetime import datetime, timezone

from src.core.config import Settings
from src.models.camera import (
    CameraRecord,
    CameraStatus,
    RTSPTransport,
    StreamDesiredState,
    StreamProtocol,
    StreamRecord,
    StreamStatus,
    ValidationStatus,
)
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.realtime_video.mediamtx import build_stream_endpoints
from src.services.realtime_video.stream_manager import WorkerSnapshot


def test_stream_contract_service_builds_frontend_ready_urls() -> None:
    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        public_api_base_url="http://localhost:8000",
        kafka_enabled=False,
        debug=False,
        _env_file=None,
    )
    service = StreamContractService(settings)
    camera = CameraRecord(
        id="cam_123",
        name="Front Gate",
        location="Gate",
        host=None,
        port=None,
        username=None,
        password=None,
        path=None,
        direct_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        transport=RTSPTransport.tcp,
        status=CameraStatus.active,
        metadata={},
        tags=[],
        last_validated_at=None,
        last_validation_status=ValidationStatus.unknown,
        last_validation_message=None,
    )
    stream_record = StreamRecord(
        camera_id="cam_123",
        stream_id="stream_cam_123",
        status=StreamStatus.running,
        desired_state=StreamDesiredState.running,
        protocol=StreamProtocol.hls,
        playback_path="http://localhost:8888/cam_123/index.m3u8",
        playlist_path="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        worker_pid=1234,
        worker_started_at=datetime.now(timezone.utc),
        last_event_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc),
        last_error_code=None,
        last_error_message=None,
        metadata={},
    )
    worker_snapshot = WorkerSnapshot(
        desired_state=StreamDesiredState.running,
        is_registered=True,
        is_process_alive=True,
        process_id=1234,
        restart_count=0,
        reconnect_attempts=0,
    )

    endpoints = build_stream_endpoints(
        "cam_123",
        rtsp_base_url="rtsp://localhost:8554",
        hls_base_url="http://localhost:8888",
        whep_base_url="http://localhost:8889",
    )
    contract = service.build_contract(camera, stream_record, worker_snapshot, endpoints)

    assert contract.playback_url == "http://localhost:8888/cam_123/index.m3u8"
    assert contract.relative_playback_url is None
    assert contract.stream_name == "cam_123"
    assert contract.access_urls.webrtc_url == "http://localhost:8889/cam_123/whep"
    assert contract.access_urls.hls_url == "http://localhost:8888/cam_123/index.m3u8"
    assert contract.websocket_url == "ws://localhost:8000/streams/ws/updates"
    assert contract.fallback is None
