"""
Cache Service — PageIndex
==========================
Redis-based caching for:
  1. Traversal results (node IDs + reasoning path) keyed by (document_id, query_hash)
  2. Frequently asked queries (full ChatResponse)

Falls back gracefully to no-op if Redis is unavailable.
"""
import json
import hashlib
from typing import Optional
from app.core.config import settings

_redis_client = None


def _get_redis():
    """Lazy initialisation with graceful fallback."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not settings.REDIS_URL or not settings.REDIS_URL.strip():
        return None
    try:
        import redis
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


def _make_key(prefix: str, document_id: str, query: str) -> str:
    query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]
    return f"pageindex:{prefix}:{document_id}:{query_hash}"


def cache_get(document_id: str, query: str, prefix: str = "chat") -> Optional[dict]:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_make_key(prefix, document_id, query))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(document_id: str, query: str, value: dict, prefix: str = "chat") -> None:
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            _make_key(prefix, document_id, query),
            settings.CACHE_TTL_SECONDS,
            json.dumps(value, default=str),
        )
    except Exception:
        pass


def cache_invalidate(document_id: str) -> int:
    r = _get_redis()
    if not r:
        return 0
    try:
        pattern = f"pageindex:*:{document_id}:*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
        return len(keys)
    except Exception:
        return 0


def is_redis_healthy() -> bool:
    r = _get_redis()
    if not r:
        return False
    try:
        r.ping()
        return True
    except Exception:
        return False
