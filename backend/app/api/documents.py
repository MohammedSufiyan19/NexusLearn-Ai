"""
NexusLearn AI — Document Routes
POST   /documents          — upload a file
GET    /documents          — list own documents
DELETE /documents/{id}     — delete own document (404 if not owner)
DELETE /me/data            — delete all own documents + chunks
GET    /documents/sources  — source list for sidebar
"""
import hashlib
import logging
import os
import secrets

from app.audit.logger import get_client_ip, log_event
from app.cache.redis_client import invalidate_user_answers
from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, get_db
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx"}
_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))


def _ensure_upload_dir():
    os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_owned_document(doc_id: str, user_id: str, db):
    """Return document or raise 404 (never 403 — don't leak existence)."""
    from app.db.models import Document
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.user_id == str(user_id),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _index_in_background(doc_id: str, user_id: str, file_path: str, filename: str, db_url: str):
    """Background task: parse, chunk, embed, update status."""
    from app.db.models import Document
    from app.db.session import SessionLocal
    from app.rag.loaders import load_document
    from app.rag.retriever import index_document

    db = SessionLocal()
    try:
        raw_docs = load_document(file_path, filename)
        for d in raw_docs:
            d.metadata["source"] = filename

        chunk_count = index_document(raw_docs, user_id, doc_id, db)

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "indexed"
            doc.page_count = len(raw_docs)
            doc.chunk_count = chunk_count
            db.commit()
        logger.info("Indexed %s: %d chunks", filename, chunk_count)
    except Exception as exc:
        logger.error("Indexing failed for %s: %s", filename, exc)
        db2 = SessionLocal()
        try:
            doc = db2.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.status = "failed"
                db2.commit()
        finally:
            db2.close()
    finally:
        db.close()
        # Clean up temp file
        try:
            os.unlink(file_path)
        except Exception:
            pass


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and index a document (returns immediately, indexing runs in background)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: .pdf .docx .pptx")

    content = await file.read()
    file_size = len(content)

    if file_size > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_file_size_mb} MB limit")

    _ensure_upload_dir()

    # Save to temp file with random name (outside web root)
    tmp_name = secrets.token_hex(16) + ext
    tmp_path = os.path.join(_UPLOAD_DIR, tmp_name)
    with open(tmp_path, "wb") as f:
        f.write(content)

    sha = _sha256_file(tmp_path)

    if db is not None:
        # Check duplicate
        from app.db.models import Document, User
        from sqlalchemy import and_
        existing = db.query(Document).filter(
            and_(Document.user_id == str(current_user.id), Document.sha256 == sha)
        ).first()
        if existing:
            os.unlink(tmp_path)
            raise HTTPException(409, f"File already uploaded as '{existing.filename}'")

        # Quota check
        user = db.query(User).filter(User.id == str(current_user.id)).first()
        if user and user.file_count >= settings.max_files_per_user:
            os.unlink(tmp_path)
            raise HTTPException(429, f"File limit reached ({settings.max_files_per_user} files max)")

        doc = Document(
            user_id=str(current_user.id),
            filename=file.filename,
            sha256=sha,
            status="pending",
            file_size_bytes=file_size,
            source_type=ext.lstrip("."),
        )
        db.add(doc)

        if user:
            user.file_count += 1
            user.total_bytes += file_size
        db.commit()
        db.refresh(doc)
        doc_id = str(doc.id)

        # Queue background indexing
        background_tasks.add_task(
            _index_in_background, doc_id, str(current_user.id),
            tmp_path, file.filename, settings.database_url
        )

        log_event(db, "upload", "success", user_id=str(current_user.id),
                  resource=file.filename, ip=get_client_ip(request))
        invalidate_user_answers(str(current_user.id))

        return {
            "message": f"'{file.filename}' received — indexing in background",
            "document_id": doc_id,
            "status": "pending",
            "file_size_bytes": file_size,
        }

    # FAISS fallback (no DB) — synchronous indexing
    from app.rag.loaders import load_document
    from app.rag.retriever import index_document

    try:
        raw_docs = load_document(tmp_path, file.filename)
        for d in raw_docs:
            d.metadata["source"] = file.filename
        chunk_count = index_document(raw_docs, str(current_user.id), "no-db", db)
        os.unlink(tmp_path)
        return {
            "message": f"'{file.filename}' indexed successfully",
            "filename": file.filename,
            "pages": len(raw_docs),
            "chunks": chunk_count,
            "status": "indexed",
        }
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise HTTPException(500, str(exc))


@router.get("/documents")
def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List own documents."""
    if db is None:
        # FAISS mode: return FAISS sources
        from app.rag.retriever import _get_faiss_store
        store = _get_faiss_store()
        if not store:
            return {"documents": []}
        seen = set()
        sources = []
        for doc in store.docstore._dict.values():
            src = doc.metadata.get("source")
            if src and src not in seen:
                seen.add(src)
                sources.append({"source": src, "source_type": doc.metadata.get("source_type")})
        return {"documents": sources}

    from app.db.models import Document
    docs = db.query(Document).filter(Document.user_id == str(current_user.id)).all()
    return {
        "documents": [
            {
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status,
                "source_type": d.source_type,
                "pages": d.page_count,
                "chunks": d.chunk_count,
                "size_bytes": d.file_size_bytes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.get("/documents/sources")
def list_sources(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sidebar-compatible source list."""
    result = list_documents(current_user=current_user, db=db)
    docs = result.get("documents", [])
    return {
        "sources": [
            {"source": d.get("filename", d.get("source")), "source_type": d.get("source_type")}
            for d in docs
        ]
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete own document. Returns 404 if not found (prevents existence leak)."""
    if db is None:
        raise HTTPException(501, "Document management requires DATABASE_URL")

    doc = _get_owned_document(document_id, str(current_user.id), db)
    db.delete(doc)

    from app.db.models import User
    user = db.query(User).filter(User.id == str(current_user.id)).first()
    if user:
        user.file_count = max(0, user.file_count - 1)
        user.total_bytes = max(0, user.total_bytes - (doc.file_size_bytes or 0))

    db.commit()

    log_event(db, "delete_document", "success", user_id=str(current_user.id),
              resource=document_id, ip=get_client_ip(request))
    invalidate_user_answers(str(current_user.id))

    return {"message": "Document deleted"}


@router.delete("/me/data")
def delete_all_my_data(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete ALL own documents and chunks. Replaces the old global /clear."""
    if db is None:
        # FAISS fallback
        import shutil
        faiss_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "vectorstore", "faiss_index")
        )
        if os.path.exists(faiss_path):
            shutil.rmtree(faiss_path)
        return {"message": "Vector store cleared"}

    from app.db.models import Document, User
    db.query(Document).filter(Document.user_id == str(current_user.id)).delete()

    user = db.query(User).filter(User.id == str(current_user.id)).first()
    if user:
        user.file_count = 0
        user.total_bytes = 0
    db.commit()

    log_event(db, "delete_all", "success", user_id=str(current_user.id), ip=get_client_ip(request))
    invalidate_user_answers(str(current_user.id))

    return {"message": "All your documents deleted"}
