from __future__ import annotations

import asyncio
import logging

import asyncpg

from src.core.config import BACKEND_ROOT, Settings

MIGRATION_DIR = BACKEND_ROOT / "scripts" / "migrations"
LOGGER = logging.getLogger(__name__)


async def ensure_migration_table(connection: asyncpg.Connection) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def applied_migrations(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch("SELECT filename FROM schema_migrations")
    return {row["filename"] for row in rows}


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    settings = Settings()
    database_url = settings.database_url
    connection = await asyncpg.connect(database_url)
    LOGGER.info("Connected to database for migrations: %s", database_url)
    try:
        await ensure_migration_table(connection)
        LOGGER.info("Ensured schema_migrations table exists.")
        already_applied = await applied_migrations(connection)
        migration_files = sorted(
            file_path
            for file_path in MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql")
            if file_path.is_file()
        )
        LOGGER.info(
            "Found %d migration files, %d already applied.",
            len(migration_files),
            len(already_applied),
        )
        for migration_path in migration_files:
            if migration_path.name in already_applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            async with connection.transaction():
                await connection.execute(sql)
                LOGGER.info(
                    "Applied migration SQL from file: %s",
                    migration_path.name,
                )
                await connection.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)",
                    migration_path.name,
                )
            LOGGER.info("Applied migration: %s", migration_path.name)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(run())
