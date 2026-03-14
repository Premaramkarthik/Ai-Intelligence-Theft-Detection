"""JWT security helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from shared.core.settings import get_settings


def create_access_token(username: str) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> str:
    """Returns username or raises JWTError."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise JWTError("JWT secret is not configured")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    username: str | None = payload.get("sub")
    if username is None:
        raise JWTError("Missing sub claim")
    return username
