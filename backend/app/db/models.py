"""
NexusLearn AI — Database Models (SQLAlchemy)
Supports PostgreSQL + pgvector (production) and SQLite (dev/testing).
"""
import uuid
from datetime import UTC, datetime

# pyrefly: ignore[missing-import]
from app.core.config import settings
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(UTC)


# Use PostgreSQL UUID type when Postgres is configured, else String for SQLite
def _uuid_col(primary_key=False, foreign_key=None):
    if settings.database_url.startswith("postgresql"):
        col_type = PG_UUID(as_uuid=True)
        default = uuid.uuid4 if primary_key else None
    else:
        col_type = String(36)
        default = _uuid if primary_key else None

    kwargs = {"default": default} if default else {}
    if foreign_key:
        return Column(col_type, ForeignKey(foreign_key, ondelete="CASCADE"),
                      nullable=not primary_key, **kwargs)
    return Column(col_type, primary_key=primary_key, nullable=not primary_key, **kwargs)


class Base(DeclarativeBase):
    pass


# ── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    role = Column(String(20), nullable=False, default="student")  # student | admin
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # Quotas
    file_count = Column(Integer, default=0, nullable=False)
    total_bytes = Column(BigInteger, default=0, nullable=False)

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


# ── Documents ────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="uq_user_sha256"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending|indexed|failed
    file_size_bytes = Column(BigInteger, default=0)
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    source_type = Column(String(10))  # pdf | docx | pptx
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    user = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


# ── Chunks ───────────────────────────────────────────────────────────────────

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), nullable=False, index=True)  # denormalized for fast filtering
    page = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    # embedding stored as JSON list for SQLite; pgvector Column added conditionally at session init
    embedding_json = Column(Text, nullable=True)  # fallback for SQLite

    document = relationship("Document", back_populates="chunks")


# ── Chat Sessions & Messages ─────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan",
                            order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)   # user | assistant | system
    content = Column(Text, nullable=False)
    route = Column(String(50), nullable=True)   # which tool was used
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


# ── Refresh Tokens (server-side revocation) ──────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 of token
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


# ── Audit Log ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)   # login | upload | delete | chat | auth_denied
    resource = Column(String(512), nullable=True)   # document id, endpoint, etc.
    ip = Column(String(50), nullable=True)
    user_agent = Column(String(512), nullable=True)
    ts = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    outcome = Column(String(20), nullable=False)    # success | failure
    detail = Column(Text, nullable=True)

    user = relationship("User", back_populates="audit_logs")
