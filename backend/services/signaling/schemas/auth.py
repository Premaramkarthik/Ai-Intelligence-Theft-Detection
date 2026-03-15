"""Auth-related Pydantic schemas."""
from pydantic import BaseModel


class TokenResponse(BaseModel):
    authenticated: bool = True
    access_token: str | None = None
    token_type: str = "cookie"


class SessionResponse(BaseModel):
    authenticated: bool
    username: str | None = None
