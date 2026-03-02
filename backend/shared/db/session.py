"""asyncpg database pool management."""
from __future__ import annotations

import asyncpg
from pathlib import Path
from shared.logging.logger import get_logger
from shared.core.settings import get_settings

log = get_logger(__name__)

class DatabaseSession:
    def __init__(self) -> None:
        self._cfg = get_settings()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._cfg.db_url,
            min_size=2,
            max_size=self._cfg.postgres_pool_size,
        )
        log.info("DB Pool created", extra={"dsn": self._cfg.db_url})

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            log.info("DB Pool closed")
            self._pool = None

    def get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected")
        return self._pool

    async def initialize_db(self, schema_path: str = "scripts/schema.sql") -> None:
        """Execute the schema SQL file to initialize the database."""
        path = Path(schema_path)
        if not path.exists():
            log.error("Schema file not found", extra={"path": schema_path})
            return

        sql = path.read_text()
        try:
            await self.connect()
            async with self._pool.acquire() as conn:
                await conn.execute(sql)
                log.info("Database schema initialized successfully")
        except Exception as e:
            log.error("Failed to initialize database schema", extra={"error": str(e)})
