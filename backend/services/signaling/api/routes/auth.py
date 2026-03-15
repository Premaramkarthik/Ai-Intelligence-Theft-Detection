"""POST /auth/token"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from shared.core.settings import get_settings
from services.signaling.api.deps import verify_jwt
from services.signaling.core.security import clear_auth_cookie, create_access_token, set_auth_cookie
from services.signaling.schemas.auth import SessionResponse, TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def login(response: Response, form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    settings = get_settings()
    try:
        settings.validate_auth_settings(require_admin_credentials=True)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if form.username != settings.admin_username or form.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")
    token = create_access_token(form.username)
    set_auth_cookie(response, token)
    return TokenResponse(authenticated=True)


@router.get("/session", response_model=SessionResponse)
async def session(_user: str = Depends(verify_jwt)) -> SessionResponse:
    return SessionResponse(authenticated=True, username=_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    clear_auth_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
