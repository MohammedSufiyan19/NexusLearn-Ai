"""
NexusLearn AI — Security Utilities
JWT creation/validation and Argon2 password hashing.
"""
from datetime import UTC, datetime, timedelta

import jwt
from app.core.config import settings
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Argon2id — current recommended default
ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plain-text password with Argon2id."""
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed. Constant-time comparison."""
    try:
        return ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def needs_rehash(hashed: str) -> bool:
    """Check if the stored hash should be upgraded."""
    try:
        return ph.check_needs_rehash(hashed)
    except Exception:
        return False


# ── JWT ──────────────────────────────────────────────────────────────────────

_TOKEN_AUDIENCE = "nexuslearn-api"
_TOKEN_ISSUER = "nexuslearn"


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "exp": expire,
        "iss": _TOKEN_ISSUER,
        "aud": _TOKEN_AUDIENCE,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create a longer-lived refresh token with unique jti nonce."""
    import secrets
    expire = datetime.now(UTC) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "exp": expire,
        "iss": _TOKEN_ISSUER,
        "aud": _TOKEN_AUDIENCE,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises jwt.InvalidTokenError on any failure.
    Never accepts alg:none.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],  # explicit allowlist — rejects alg:none
        audience=_TOKEN_AUDIENCE,
        issuer=_TOKEN_ISSUER,
    )
