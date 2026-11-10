"""
NexusLearn AI — Audit Logger
Writes security-relevant events to the audit_log table.
Logs: login success/fail, upload, delete, chat (metadata only), auth denials.
Never logs raw document text or full prompts.
"""
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def log_event(
    db,
    action: str,
    outcome: str,
    user_id: str | None = None,
    resource: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: str | None = None,
):
    """
    Write an audit event.
    db: SQLAlchemy session (may be None in FAISS-only mode — falls back to logger)

    Actions: login_success | login_failure | register | upload | delete_document |
             delete_all | chat | auth_denied | rate_limited | logout
    Outcomes: success | failure
    """
    if db is None:
        # Fallback: structured log entry
        logger.info(
            "AUDIT action=%s outcome=%s user=%s resource=%s ip=%s",
            action, outcome, user_id, resource, ip,
        )
        return

    try:
        from app.db.models import AuditLog
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            ip=ip,
            user_agent=user_agent,
            ts=datetime.now(UTC),
            outcome=outcome,
            detail=detail,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc)
        db.rollback()


def get_client_ip(request) -> str:
    """Extract real client IP from request (handles X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
