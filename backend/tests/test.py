import asyncio
import os
import socket

import asyncpg

# Provide connection values via environment variables for safety
DB_HOST = os.getenv("DB_HOST", "db.ehqzpadhcppgyvuqagpy.supabase.co")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")  # set your password in the environment
SSL = os.getenv("DB_SSL", "require")  # 'require' or 'disable'


async def test_connection() -> None:
    conn = None
    try:
        print(f"Resolving host {DB_HOST}...")
        try:
            ip = socket.gethostbyname(DB_HOST)
            print(f"Resolved {DB_HOST} -> {ip}")
        except OSError as exc:
            print(f"DNS resolution failed: {exc}")
            return

        print("Connecting to the database...")
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            ssl=SSL if SSL.lower() != "disable" else False,
            timeout=5.0,
        )
        print("Connected. Running test query...")
        row = await conn.fetchrow("SELECT now() AS server_time;")
        print("Query result:", row["server_time"])
    except (OSError, asyncpg.PostgresError) as exc:
        print("Connection failed:", exc)
    finally:
        if conn:
            await conn.close()
            print("Connection closed.")


if __name__ == "__main__":
    asyncio.run(test_connection())
