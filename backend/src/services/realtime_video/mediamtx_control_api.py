"""Control API helpers for synchronizing runtime MediaMTX path configuration."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class MediaMtxControlApiException(RuntimeError):
    """Raise when MediaMTX Control API operations fail."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Create a structured MediaMTX Control API error."""

        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class MediaMtxControlApiClient:
    """Synchronize MediaMTX path configuration through its runtime Control API."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        username: str,
        password: str,
    ) -> None:
        """Create a Control API client for a specific MediaMTX deployment."""

        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._authorization_header = _build_basic_authorization_header(
            username,
            password,
        )

    async def list_configured_paths(self) -> dict[str, dict[str, Any]]:
        """Return the configured MediaMTX paths keyed by their runtime name."""

        payload = await self._request_json("GET", "/v3/config/paths/list")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise MediaMtxControlApiException(
                "MediaMTX Control API returned an invalid paths list payload.",
            )

        configured_paths: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                configured_paths[name] = item
        return configured_paths

    async def path_exists(self, path_name: str) -> bool:
        """Return whether a path is currently present in MediaMTX runtime config."""

        path = f"/v3/config/paths/get/{quote(path_name, safe='')}"
        try:
            await self._request_json("GET", path)
        except MediaMtxControlApiException as exc:
            if "HTTP 404" in str(exc):
                return False
            raise
        return True

    async def add_path(self, path_name: str, payload: dict[str, Any]) -> None:
        """Create a new MediaMTX path through the Control API."""

        path = f"/v3/config/paths/add/{quote(path_name, safe='')}"
        await self._request_json("POST", path, payload)

    async def patch_path(self, path_name: str, payload: dict[str, Any]) -> None:
        """Update an existing MediaMTX path through the Control API."""

        path = f"/v3/config/paths/patch/{quote(path_name, safe='')}"
        await self._request_json("PATCH", path, payload)

    async def delete_path(self, path_name: str) -> None:
        """Delete a MediaMTX path through the Control API when it is no longer desired."""

        path = f"/v3/config/paths/delete/{quote(path_name, safe='')}"
        await self._request_json("DELETE", path)

    async def upsert_path(
        self,
        path_name: str,
        payload: dict[str, Any],
        configured_paths: dict[str, dict[str, Any]],
    ) -> None:
        """Create or update a runtime MediaMTX path depending on whether it already exists."""

        if path_name in configured_paths:
            await self.patch_path(path_name, payload)
            return
        await self.add_path(path_name, payload)

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a JSON Control API request and decode the JSON response body."""

        return await asyncio.to_thread(
            self._request_json_blocking,
            method,
            path,
            payload,
        )

    def _request_json_blocking(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a blocking HTTP request against MediaMTX and decode the JSON response."""

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url=f"{self._base_url}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._authorization_header,
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                raw_payload = response.read()
        except HTTPError as exc:
            raise MediaMtxControlApiException(
                f"MediaMTX Control API request failed with HTTP {exc.code} for {path}.",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise MediaMtxControlApiException(
                f"MediaMTX Control API request failed for {path}: {exc.reason}.",
                reason=str(exc.reason),
            ) from exc

        if not raw_payload:
            return {}
        try:
            decoded = json.loads(raw_payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MediaMtxControlApiException(
                f"MediaMTX Control API returned invalid JSON for {path}.",
            ) from exc

        if not isinstance(decoded, dict):
            raise MediaMtxControlApiException(
                f"MediaMTX Control API returned an unexpected payload type for {path}.",
            )
        return decoded


def _build_basic_authorization_header(username: str, password: str) -> str:
    """Build an HTTP Basic authorization header for MediaMTX Control API requests."""

    encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {encoded}"
