"""JWT security helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Response
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


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
