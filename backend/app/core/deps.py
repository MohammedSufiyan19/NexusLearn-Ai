"""
NexusLearn AI — FastAPI Dependencies
Provides get_current_user, get_db, get_redis for route injection.
"""
import jwt
from app.core.config import settings
from app.core.security import decode_token
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


# ── Database Session ─────────────────────────────────────────────────────────

def get_db():
    """
    Yields a SQLAlchemy Session.
    Uses PostgreSQL if configured, else SQLite (local dev/testing).
    """
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Redis Client ─────────────────────────────────────────────────────────────

def get_redis():
    """
    Returns a Redis client if REDIS_URL is configured.
    Falls back to None (no caching).
    """
    if not settings.redis_url:
        return None
    try:
        from app.cache.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


# ── Auth ─────────────────────────────────────────────────────────────────────

class CurrentUser:
    """Lightweight user object extracted from JWT — no DB hit required."""
    def __init__(self, user_id: str, email: str, role: str):
        self.id = user_id
        self.email = email
        self.role = role

    def __repr__(self):
        return f"<CurrentUser id={self.id} role={self.role}>"


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Validates Bearer token and returns CurrentUser.
    Raises 401 if token is missing, expired, or tampered.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    email = payload.get("email", "")
    role = payload.get("role", "student")

    if not user_id:
        raise credentials_exception

    return CurrentUser(user_id=user_id, email=email, role=role)


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that additionally requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
