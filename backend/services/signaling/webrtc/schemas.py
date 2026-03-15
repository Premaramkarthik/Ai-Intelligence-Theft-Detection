from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IceServerConfig(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class WebRTCOfferRequest(BaseModel):
    sdp: str = Field(min_length=1)
    type: Literal["offer"] = "offer"


class WebRTCAnswerResponse(BaseModel):
    session_id: str
    sdp: str
    type: Literal["answer"] = "answer"
    ice_servers: list[IceServerConfig]
    preview_transport: Literal["webrtc"] = "webrtc"


class WebRTCConfigResponse(BaseModel):
    ice_servers: list[IceServerConfig]
    preview_transport: Literal["webrtc"] = "webrtc"


class WebRTCSessionInfo(BaseModel):
    session_id: str
    camera_id: str
    state: Literal["connecting", "connected", "closed"]
