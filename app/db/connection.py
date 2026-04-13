import asyncpg
from app.core.config import settings

from tenacity import retry, stop_after_attempt, wait_fixed
import logging

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


@retry(stop=stop_after_attempt(10), wait=wait_fixed(5))
async def create_pool() -> asyncpg.Pool:
    global _pool
    logger.info("Connecting to database pool...")
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("Database pool connected successfully.")
        return _pool
    except Exception as e:
        logger.error(f"Database connection attempt failed: {e}. Retrying...")
        raise e


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
