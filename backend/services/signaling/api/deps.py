"""Dependency injection for Signaling routes."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from services.signaling.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


async def verify_jwt(token: str = Depends(oauth2_scheme)) -> str:
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
