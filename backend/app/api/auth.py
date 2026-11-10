"""
NexusLearn AI — Authentication Routes
POST /auth/register  — create account
POST /auth/login     — returns access + refresh tokens
POST /auth/refresh   — exchange refresh token for new access token
POST /auth/logout    — revoke refresh token
"""
import hashlib
import logging
from datetime import UTC, datetime, timedelta

from app.audit.logger import get_client_ip, log_event
from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response Models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_db(db):
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Auth requires DATABASE_URL — running in demo mode (no auth)",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Register a new user account."""
    _check_db(db)
    from app.db.models import User

    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_event(db, "register", "success", user_id=str(user.id),
              ip=get_client_ip(request), resource=req.email)

    return {"message": "Account created", "user_id": str(user.id)}


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    _check_db(db)
    from app.db.models import RefreshToken, User

    ip = get_client_ip(request)
    user = db.query(User).filter(User.email == req.email).first()

    if not user or not verify_password(req.password, user.password_hash):
        log_event(db, "login_failure", "failure", ip=ip, resource=req.email,
                  detail="Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Re-hash if Argon2 params changed
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
        db.commit()

    access = create_access_token(str(user.id), user.email, user.role)
    refresh = create_refresh_token(str(user.id))

    # Store refresh token hash server-side for revocation
    rt = RefreshToken(
        user_id=str(user.id),
        token_hash=_token_hash(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    db.commit()

    log_event(db, "login_success", "success", user_id=str(user.id), ip=ip)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh pair."""
    _check_db(db)
    from app.db.models import RefreshToken, User

    try:
        payload = decode_token(req.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    token_hash = _token_hash(req.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
    ).first()

    if not stored:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate: revoke old, issue new
    stored.revoked = True
    new_access = create_access_token(str(user.id), user.email, user.role)
    new_refresh = create_refresh_token(str(user.id))

    new_rt = RefreshToken(
        user_id=str(user.id),
        token_hash=_token_hash(new_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_rt)
    db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
def logout(req: RefreshRequest, current_user: CurrentUser = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Revoke the supplied refresh token."""
    _check_db(db)
    from app.db.models import RefreshToken

    token_hash = _token_hash(req.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == str(current_user.id),
    ).first()

    if stored:
        stored.revoked = True
        db.commit()
        log_event(db, "logout", "success", user_id=str(current_user.id))

    return {"message": "Logged out"}


@router.get("/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Return current user info from JWT (no DB hit)."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }
