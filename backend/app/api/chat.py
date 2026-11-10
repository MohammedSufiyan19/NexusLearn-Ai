"""
NexusLearn AI — Chat Route
POST /chat — authenticated, per-user scoped retrieval
Includes rate limiting, answer caching, and audit logging.
"""
import logging

from app.audit.logger import get_client_ip, log_event
from app.cache.redis_client import (
    check_rate_limit,
    get_cached_answer,
    get_request_count,
    set_cached_answer,
)
from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, get_db
from app.rag.generator import build_sources, generate
from app.rag.retriever import search
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


# ── Route classification ──────────────────────────────────────────────────────

_ROUTE_KEYWORDS = {
    "topic_explainer": ["explain", "what is", "define", "describe", "concept", "meaning"],
    "question_solver": ["solve", "calculate", "find", "prove", "question", "q1", "q2", "q3", "q4", "q5", "answer"],
    "learning_path_generator": ["study plan", "schedule", "prepare", "exam in", "days left", "learning path"],
    "content_synthesizer": ["compare", "contrast", "both", "all sources", "synthesize", "combine"],
}


def _classify_query(query: str, has_docs: bool) -> str:
    """Fast keyword-based router (no LLM cost for classification)."""
    if not has_docs:
        return "chat"
    q_lower = query.lower()
    for route, keywords in _ROUTE_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            return route
    return "topic_explainer"  # default RAG mode


def _get_doc_set_version(user_id: str, db) -> str:
    """Returns a string that changes when the user's documents change (for cache keying)."""
    if db is None:
        return "faiss"
    try:
        from app.db.models import Document
        docs = db.query(Document.id, Document.created_at).filter(
            Document.user_id == str(user_id), Document.status == "indexed"
        ).all()
        ids = sorted(str(d.id) for d in docs)
        import hashlib
        return hashlib.md5("|".join(ids).encode()).hexdigest()[:8]
    except Exception:
        return "unknown"


# ── Request / Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 4000:
            raise ValueError("Message too long (max 4000 chars)")
        return v


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] = []
    route: str = "chat"
    provider: str | None = None
    cached: bool = False


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Main chat endpoint.
    - Rate limited per user
    - Answer cached per user + document set version
    - Retrieval scoped to current user only
    """
    user_id = str(current_user.id)

    # ── Rate limit ────────────────────────────────────────────────────────
    if not check_rate_limit(user_id, settings.max_requests_per_day):
        count = get_request_count(user_id)
        log_event(db, "rate_limited", "failure", user_id=user_id, ip=get_client_ip(request),
                  detail=f"Count: {count}")
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {settings.max_requests_per_day} requests reached. Try again tomorrow.",
        )

    # ── Answer cache check ────────────────────────────────────────────────
    doc_version = _get_doc_set_version(user_id, db)
    cached = get_cached_answer(user_id, doc_version, req.message)
    if cached:
        log_event(db, "chat", "success", user_id=user_id,
                  detail=f"cache_hit route={cached.get('route')}")
        return ChatResponse(**cached, cached=True)

    # ── Classify query ────────────────────────────────────────────────────
    # Check if user has documents
    has_docs = False
    if db is not None:
        from app.db.models import Document
        has_docs = db.query(Document.id).filter(
            Document.user_id == user_id, Document.status == "indexed"
        ).first() is not None
    else:
        from app.rag.retriever import _get_faiss_store
        has_docs = _get_faiss_store() is not None

    route = _classify_query(req.message, has_docs)

    # ── Retrieve ──────────────────────────────────────────────────────────
    chunks = []
    if route != "chat":
        chunks = search(
            query=req.message,
            user_id=user_id,
            db=db,
            k=settings.default_top_k,
        )

    # ── Generate ──────────────────────────────────────────────────────────
    provider_log = []
    try:
        answer = generate(
            query=req.message,
            route=route,
            chunks=chunks,
            history=req.history,
            provider_log=provider_log,
        )
    except Exception as exc:
        logger.error("Generation failed: %s", exc)
        raise HTTPException(500, "Generation failed — please try again")

    sources = build_sources(chunks)
    provider = provider_log[0] if provider_log else None

    response_data = {
        "answer": answer,
        "sources": sources,
        "route": route,
        "provider": provider,
    }

    # ── Cache answer ──────────────────────────────────────────────────────
    if route != "chat" and chunks:
        set_cached_answer(user_id, doc_version, req.message, response_data)

    # ── Audit log (metadata only — no raw content) ────────────────────────
    log_event(
        db, "chat", "success", user_id=user_id,
        ip=get_client_ip(request),
        detail=f"route={route} provider={provider} sources={len(sources)}",
    )

    return ChatResponse(**response_data, cached=False)
