"""Dependency injection for Signaling routes."""
from __future__ import annotations

from typing import Mapping

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, WebSocket, status
from jose import JWTError

from services.signaling.core.security import decode_token
from shared.core.settings import get_settings


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    return None


def _extract_cookie_token(cookies: Mapping[str, str] | None) -> str | None:
    if not cookies:
        return None
    settings = get_settings()
    token = cookies.get(settings.auth_cookie_name)
    return token.strip() if token else None


def _extract_request_token(request: Request) -> str | None:
    return _extract_cookie_token(request.cookies) or _extract_bearer_token(request.headers.get("authorization"))


async def verify_jwt(request: Request) -> str:
    token = _extract_request_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_ws_token(websocket: WebSocket) -> str:
    token = _extract_cookie_token(getattr(websocket, "cookies", None))
    if not token:
        token = _extract_bearer_token(websocket.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication")
    try:
        return decode_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
