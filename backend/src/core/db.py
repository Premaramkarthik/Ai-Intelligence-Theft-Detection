from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

import asyncpg

from src.core.config import Settings
from src.core.exceptions.database.database_exceptions import DatabaseUnavailableException
from src.utils.sql_loader import SqlQueryLoader

Fetcher = Literal["execute", "fetch", "fetchrow", "fetchval"]


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None
        self._sql_loader = SqlQueryLoader()

    async def connect(self) -> None:
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.database_url,
                min_size=self._settings.db_pool_min_size,
                max_size=self._settings.db_pool_max_size,
                init=self._init_connection,
            )
        except (OSError, asyncpg.PostgresError) as exc:
            masked_dsn = _mask_dsn(self._settings.database_url)
            raise DatabaseUnavailableException(
                "Could not connect to PostgreSQL using DATABASE_URL="
                f"'{masked_dsn}'. Start PostgreSQL or point DATABASE_URL "
                "to a reachable database."
            ) from exc

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise DatabaseUnavailableException("Database pool is not initialized.")
        return self._pool

    async def _init_connection(self, connection: asyncpg.Connection) -> None:
        await connection.set_type_codec(
            "json",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        await connection.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def run_sql(self, relative_path: str, fetcher: Fetcher, *params: Any) -> Any:
        query = self._sql_loader.load(self._settings.sql_dir / relative_path)
        async with self.pool.acquire() as connection:
            method: Callable[..., Any] = getattr(connection, fetcher)
            return await method(query, *params)

    async def execute_file(self, relative_path: str, *params: Any) -> str:
        return await self.run_sql(relative_path, "execute", *params)

    async def fetch_file(self, relative_path: str, *params: Any) -> list[Any]:
        return await self.run_sql(relative_path, "fetch", *params)

    async def fetchrow_file(self, relative_path: str, *params: Any) -> Any:
        return await self.run_sql(relative_path, "fetchrow", *params)

    async def fetchval_file(self, relative_path: str, *params: Any) -> Any:
        return await self.run_sql(relative_path, "fetchval", *params)

    async def ping(self) -> bool:
        result = await self.fetchval_file("common/health_check.sql")
        return result == 1


def _mask_dsn(dsn: str) -> str:
    parsed = urlsplit(dsn)
    if "@" not in parsed.netloc:
        return dsn

    credentials, host = parsed.netloc.rsplit("@", maxsplit=1)
    if ":" in credentials:
        username, _password = credentials.split(":", maxsplit=1)
        netloc = f"{username}:****@{host}"
    else:
        netloc = f"****@{host}"

    return urlunsplit(
        SplitResult(
            scheme=parsed.scheme,
            netloc=netloc,
            path=parsed.path,
            query=parsed.query,
            fragment=parsed.fragment,
        )
    )
