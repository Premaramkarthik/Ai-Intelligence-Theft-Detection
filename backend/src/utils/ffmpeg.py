from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from src.models.camera import CameraRecord, RTSPTransport


def normalize_camera_path(path: str | None) -> str:
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def build_rtsp_url(
    *,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    path: str | None,
    direct_rtsp_url: str | None,
) -> str:
    if direct_rtsp_url:
        return direct_rtsp_url

    if host is None or path is None:
        raise ValueError("Camera source is missing host/path or direct RTSP URL.")

    credentials = ""
    if username:
        credentials = quote(username, safe="")
        if password:
            credentials = f"{credentials}:{quote(password, safe='')}"
        credentials = f"{credentials}@"

    resolved_port = port or 554
    return f"rtsp://{credentials}{host}:{resolved_port}{normalize_camera_path(path)}"


def build_rtsp_url_from_camera(camera: CameraRecord) -> str:
    return build_rtsp_url(
        host=camera.host,
        port=camera.port,
        username=camera.username,
        password=camera.password,
        path=camera.path,
        direct_rtsp_url=camera.direct_rtsp_url,
    )


def mask_rtsp_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    prefix, rest = url.split("://", maxsplit=1)
    credentials, host_path = rest.split("@", maxsplit=1)
    if ":" in credentials:
        user, _password = credentials.split(":", maxsplit=1)
        return f"{prefix}://{user}:****@{host_path}"
    return f"{prefix}://****@{host_path}"


def build_hls_output_paths(
    media_root: Path,
    hls_directory_name: str,
    camera_id: str,
) -> tuple[Path, Path]:
    output_dir = media_root / hls_directory_name / camera_id
    playlist_path = output_dir / "index.m3u8"
    return output_dir, playlist_path


def build_ffmpeg_hls_command(
    ffmpeg_binary: str,
    rtsp_url: str,
    transport: RTSPTransport | str,
    playlist_path: Path,
    segment_time_seconds: int,
    playlist_size: int,
) -> list[str]:
    transport_value = transport.value if isinstance(transport, RTSPTransport) else transport
    segment_pattern = str(playlist_path.parent / "segment_%06d.ts")
    return [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",
        "-rtsp_transport",
        transport_value,
        "-i",
        rtsp_url,
        "-an",
        "-c:v",
        "copy",
        "-f",
        "hls",
        "-hls_time",
        str(segment_time_seconds),
        "-hls_list_size",
        str(playlist_size),
        "-hls_flags",
        "delete_segments+append_list+independent_segments+program_date_time",
        "-hls_segment_filename",
        segment_pattern,
        str(playlist_path),
    ]
