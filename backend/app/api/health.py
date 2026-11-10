"""
NexusLearn AI — Health & Status Routes
"""
from app.core.config import settings
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"status": "NexusLearn AI is running", "version": "2.0.0"}


@router.get("/health")
def health():
    """Detailed health check."""
    db_mode = "postgres" if settings.database_url.startswith("postgresql") \
        else ("sqlite" if settings.database_url else "faiss")
    redis_ok = False
    if settings.redis_url:
        try:
            from app.cache.redis_client import get_redis_client
            r = get_redis_client()
            redis_ok = r is not None and bool(r.ping())
        except Exception:
            pass

    return {
        "status": "ok",
        "db_mode": db_mode,
        "redis": "connected" if redis_ok else ("not configured" if not settings.redis_url else "unreachable"),
        "auth": "enabled" if settings.database_url else "disabled (demo mode)",
        "environment": settings.environment,
    }
