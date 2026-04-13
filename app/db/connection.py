import asyncpg
from app.core.config import settings

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_db() -> asyncpg.Connection:
    """FastAPI dependency — yields a connection from the pool."""
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Server may still be starting up.")
    async with _pool.acquire() as conn:
        yield conn
