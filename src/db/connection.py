from typing import AsyncGenerator

import asyncpg

from src.core.config import settings

pool: asyncpg.Pool | None = None


async def connect_to_db() -> None:
    """Init connection pool with postgreSQL"""
    global pool
    try:
        pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL, min_size=2, max_size=10
        )
        print("Connected with postgres db")
    except Exception as e:
        print(f"Error connection with db: {e}")
        raise e


async def close_db_connection() -> None:
    """Close the connection pool when closing an app"""
    global pool

    if pool is not None:
        await pool.close()
        print("Connection pool closed")


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency Injection returns an active connection from the pool"""
    if pool is None:
        raise Exception("Connection pool not initialized")

    connection = await pool.acquire()
    try:
        yield connection
    finally:
        try:
            await pool.release(connection)
        except AttributeError:
            pass
