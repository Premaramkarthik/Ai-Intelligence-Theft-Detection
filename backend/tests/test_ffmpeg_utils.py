from pathlib import Path

from src.models.camera import RTSPTransport
from src.utils.ffmpeg import (
    build_ffmpeg_hls_command,
    build_ffmpeg_rtsp_publish_command,
    mask_rtsp_url,
)


def test_build_ffmpeg_hls_command_contains_hls_output() -> None:
    command = build_ffmpeg_hls_command(
        ffmpeg_binary="ffmpeg",
        rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        transport=RTSPTransport.tcp,
        playlist_path=Path("/tmp/index.m3u8"),
        segment_time_seconds=2,
        playlist_size=6,
    )
    assert command[0] == "ffmpeg"
    assert "-f" in command
    assert "hls" in command
    assert "-fflags" in command
    assert "+genpts" in command
    assert "-use_wallclock_as_timestamps" in command
    assert "1" in command
    assert str(Path("/tmp/index.m3u8")) == command[-1]


def test_mask_rtsp_url_hides_password() -> None:
    masked = mask_rtsp_url("rtsp://192.168.1.2:8080/h264_ulaw.sdp")
    assert masked == "rtsp://192.168.1.2:8080/h264_ulaw.sdp"


def test_build_ffmpeg_rtsp_publish_command_contains_rawvideo_input() -> None:
    command = build_ffmpeg_rtsp_publish_command(
        "ffmpeg",
        "rtsp://localhost:8554/front_gate_tracked",
        width=1280,
        height=720,
        fps=5.0,
        transport=RTSPTransport.tcp,
    )

    assert command[0] == "ffmpeg"
    assert "-f" in command
    assert "rawvideo" in command
    assert "bgr24" in command
    assert "libx264" in command
    assert command[-1] == "rtsp://localhost:8554/front_gate_tracked"
