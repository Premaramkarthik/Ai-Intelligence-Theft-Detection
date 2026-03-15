from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urlparse

import cv2

from shared.core.settings import get_settings
from shared.logging.logger import get_logger

log = get_logger(__name__)
_ALLOWED_NETWORK_SCHEMES = {"rtsp", "rtsps", "http", "https"}


def _is_disallowed_ip(address: ipaddress._BaseAddress) -> bool:
    settings = get_settings()
    if settings.reject_loopback_camera_hosts and (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        return True
    if not settings.allow_private_camera_hosts and address.is_private:
        return True
    return False


def _validate_network_source_shape(src: str) -> bool:
    settings = get_settings()
    raw = src.strip()
    if not raw or len(raw) > settings.max_source_url_length:
        return False
    if any(ord(char) < 32 for char in raw):
        return False

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in _ALLOWED_NETWORK_SCHEMES:
        return False
    if not parsed.hostname:
        return False
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        return False

    try:
        candidate = ipaddress.ip_address(parsed.hostname)
        return not _is_disallowed_ip(candidate)
    except ValueError:
        if parsed.hostname.lower() == "localhost":
            return False

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, parsed.port or 0, type=socket.SOCK_STREAM)
    except OSError:
        return False

    for _family, _socktype, _proto, _canonname, sockaddr in addrinfo:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_disallowed_ip(address):
            return False
    return True


def validate_source(src: str | int, timeout_s: float = 3.0) -> bool:
    if isinstance(src, int):
        if src < 0 or src > 32:
            return False
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
    else:
        if not _validate_network_source_shape(src):
            return False
        cap = cv2.VideoCapture(src)

    try:
        start = time.time()
        while time.time() - start < timeout_s:
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    return True
            time.sleep(0.1)
        return False
    except Exception as exc:
        log.error("Validation error", extra={"error": str(exc)})
        return False
    finally:
        cap.release()
