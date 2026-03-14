"""POST /auth/token"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from shared.core.settings import get_settings
from services.signaling.core.security import create_access_token
from services.signaling.schemas.auth import TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    settings = get_settings()
    if not settings.admin_username or not settings.admin_password or not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    if form.username != settings.admin_username or form.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")
    token = create_access_token(form.username)
    return TokenResponse(access_token=token)
