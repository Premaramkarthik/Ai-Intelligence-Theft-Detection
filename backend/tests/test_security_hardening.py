from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import JWTError

from services.signaling.api.deps import verify_ws_token
from services.signaling.api.routes import auth
from shared.core.settings import Settings, get_settings
from shared.validation.video_source import validate_source


@dataclass
class FakeWebSocket:
    query_params: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.query_params = self.query_params or {}
        self.headers = self.headers or {}
        self.cookies = self.cookies or {}


def test_verify_ws_token_accepts_cookie(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("services.signaling.api.deps.decode_token", lambda token: f"user:{token}")

    user = verify_ws_token(FakeWebSocket(cookies={"pipeline_access_token": "cookie-token"}))  # type: ignore[arg-type]

    assert user == "user:cookie-token"


def test_verify_ws_token_rejects_query_param_only(monkeypatch: pytest.MonkeyPatch):
    def _raise(_token: str) -> str:
        raise JWTError("invalid")

    monkeypatch.setattr("services.signaling.api.deps.decode_token", _raise)

    with pytest.raises(HTTPException):
        verify_ws_token(FakeWebSocket(query_params={"token": "leaky-token"}))  # type: ignore[arg-type]


def test_auth_cookie_session_round_trip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "password123")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    client = TestClient(app)

    response = client.post("/auth/token", data={"username": "admin", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    set_cookie = response.headers["set-cookie"]
    assert "pipeline_access_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    session = client.get("/auth/session")
    assert session.status_code == 200
    assert session.json() == {"authenticated": True, "username": "admin"}

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    after_logout = client.get("/auth/session")
    assert after_logout.status_code == 401

    get_settings.cache_clear()


def test_settings_reject_weak_jwt_secret():
    settings = Settings(
        _env_file=None,
        jwt_secret="short-secret",
        admin_username="admin",
        admin_password="password123",
    )

    with pytest.raises(RuntimeError):
        settings.validate_auth_settings(require_admin_credentials=True)


def test_validate_source_rejects_loopback_rtsp():
    assert validate_source("rtsp://127.0.0.1:554/stream", timeout_s=0.0) is False
