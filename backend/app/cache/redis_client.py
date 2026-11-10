"""
NexusLearn AI — Redis Cache Client
Embedding cache, answer cache, rate limiting.
Graceful degradation: all functions are no-ops if Redis is unavailable.
"""
import hashlib
import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def get_redis_client():
    """Lazy singleton Redis client. Returns None if REDIS_URL is empty."""
    global _client
    if _client is not None:
        return _client
    if not settings.redis_url:
        return None
    try:
        import redis
        _client = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
        _client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
        return _client
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — running without cache", exc)
        return None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ── Embedding Cache ──────────────────────────────────────────────────────────

def get_cached_embedding(text: str) -> list | None:
    """Return cached embedding vector or None."""
    r = get_redis_client()
    if not r:
        return None
    try:
        key = f"emb:{_sha(text)}"
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def set_cached_embedding(text: str, embedding: list):
    """Cache an embedding vector permanently (no TTL — text content is immutable)."""
    r = get_redis_client()
    if not r:
        return
    try:
        key = f"emb:{_sha(text)}"
        r.set(key, json.dumps(embedding))
    except Exception:
        pass


# ── Answer Cache ─────────────────────────────────────────────────────────────

def _answer_key(user_id: str, doc_set_version: str, question: str) -> str:
    """
    Key includes user_id + doc-set version to prevent cross-user leakage.
    doc_set_version should change whenever the user's document set changes.
    """
    return f"ans:{user_id}:{doc_set_version}:{_sha(question.lower().strip())}"


def get_cached_answer(user_id: str, doc_set_version: str, question: str) -> dict | None:
    """Return cached answer dict or None."""
    r = get_redis_client()
    if not r:
        return None
    try:
        val = r.get(_answer_key(user_id, doc_set_version, question))
        return json.loads(val) if val else None
    except Exception:
        return None


def set_cached_answer(user_id: str, doc_set_version: str, question: str,
                      answer: dict, ttl: int = 3600):
    """Cache an answer for TTL seconds (default 1 hour). Invalidated by doc_set_version."""
    r = get_redis_client()
    if not r:
        return
    try:
        r.setex(_answer_key(user_id, doc_set_version, question), ttl, json.dumps(answer))
    except Exception:
        pass


def invalidate_user_answers(user_id: str):
    """Invalidate all cached answers for a user (called after upload/delete)."""
    r = get_redis_client()
    if not r:
        return
    try:
        pattern = f"ans:{user_id}:*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass


# ── Rate Limiting ────────────────────────────────────────────────────────────

def check_rate_limit(user_id: str, max_per_day: int) -> bool:
    """
    Returns True if the request is within the daily limit.
    Uses a 24-hour sliding window counter keyed by user_id.
    """
    r = get_redis_client()
    if not r:
        return True  # no Redis → no rate limiting (graceful degradation)
    try:
        key = f"rate:{user_id}:daily"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 86400)  # 24 hours
        return count <= max_per_day
    except Exception:
        return True  # fail open


def get_request_count(user_id: str) -> int:
    """Return current daily request count for a user."""
    r = get_redis_client()
    if not r:
        return 0
    try:
        val = r.get(f"rate:{user_id}:daily")
        return int(val) if val else 0
    except Exception:
        return 0
