from pathlib import Path

from src.models.camera import RTSPTransport
from src.utils.ffmpeg import build_ffmpeg_hls_command, mask_rtsp_url


def test_build_ffmpeg_hls_command_contains_hls_output() -> None:
    command = build_ffmpeg_hls_command(
        ffmpeg_binary="ffmpeg",
        rtsp_url="rtsp://user:pass@camera.local:554/stream",
        transport=RTSPTransport.tcp,
        playlist_path=Path("/tmp/index.m3u8"),
        segment_time_seconds=2,
        playlist_size=6,
    )
    assert command[0] == "ffmpeg"
    assert "-f" in command
    assert "hls" in command
    assert str(Path("/tmp/index.m3u8")) == command[-1]


def test_mask_rtsp_url_hides_password() -> None:
    masked = mask_rtsp_url("rtsp://user:supersecret@camera.local:554/live")
    assert masked == "rtsp://user:****@camera.local:554/live"
