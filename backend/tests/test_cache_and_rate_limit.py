"""
Tests for Redis Caching, Cache Scoping & Rate Limiting (Phase 5).
Verifies:
  - Cache keys are scoped to user_id + doc_set_version (preventing cross-user cache poisoning)
  - Functions degrade gracefully to no-ops when Redis is unavailable
  - Daily request counting and rate limit checks
"""
from unittest.mock import MagicMock, patch

from app.cache.redis_client import (
    _answer_key,
    check_rate_limit,
    get_cached_answer,
    invalidate_user_answers,
    set_cached_answer,
)


def test_answer_cache_key_isolation():
    """
    Two users asking the exact same question MUST produce distinct cache keys.
    Changing the doc_set_version must also produce a distinct cache key.
    """
    q = "What is ACID in DBMS?"
    key_user_a = _answer_key(user_id="user-1", doc_set_version="v1", question=q)
    key_user_b = _answer_key(user_id="user-2", doc_set_version="v1", question=q)
    key_user_a_v2 = _answer_key(user_id="user-1", doc_set_version="v2", question=q)

    assert key_user_a != key_user_b, "Cache keys between users must never collide"
    assert key_user_a != key_user_a_v2, "Cache key must change when document set is updated"
    assert "user-1" in key_user_a
    assert "user-2" in key_user_b


def test_graceful_degradation_without_redis():
    """When Redis is not configured, cache functions return None and do not crash."""
    with patch("app.cache.redis_client.get_redis_client", return_value=None):
        assert get_cached_answer("u1", "v1", "any question") is None
        # set_cached_answer and invalidate_user_answers should execute without exception
        set_cached_answer("u1", "v1", "any question", {"answer": "test"})
        invalidate_user_answers("u1")
        # Rate limit fails open (returns True)
        assert check_rate_limit("u1", max_per_day=10) is True


def test_rate_limiting_enforced_with_redis():
    """Rate limiter enforces limit when counter exceeds max_per_day."""
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 101  # Exceeds max 100

    with patch("app.cache.redis_client.get_redis_client", return_value=mock_redis):
        allowed = check_rate_limit("user-busy", max_per_day=100)
        assert allowed is False

    mock_redis.incr.return_value = 5  # Within limit
    with patch("app.cache.redis_client.get_redis_client", return_value=mock_redis):
        allowed = check_rate_limit("user-normal", max_per_day=100)
        assert allowed is True
