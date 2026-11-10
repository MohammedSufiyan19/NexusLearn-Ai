"""
Tests for Persistence & Multi-User Isolation (Phase 2 & Phase 3).
The most critical security test in the repo.
Verifies:
  - User B cannot retrieve User A's document chunks
  - User B cannot DELETE User A's document (returns 404, not 403, preventing IDOR & existence leakage)
  - /me/data only clears the caller's data and leaves other users untouched
  - User document lists are strictly isolated
"""
from app.core.security import create_access_token
from app.db.models import Chunk, Document, User
from app.rag.retriever import search


def _create_user(db, email, user_id):
    u = User(id=user_id, email=email, password_hash="argon2id$mocked", role="student")
    db.add(u)
    db.commit()
    return u


def test_user_b_cannot_delete_user_a_document(client, db):
    """
    OWASP BOLA / IDOR test:
    User B attempting to DELETE User A's document MUST receive 404 (not 403).
    404 prevents leaking whether the resource exists.
    """
    user_a = _create_user(db, "user_a@test.com", "user-aaa")
    user_b = _create_user(db, "user_b@test.com", "user-bbb")

    # User A owns a document
    doc_a = Document(
        id="doc-secret-a",
        user_id=user_a.id,
        filename="confidential_research.pdf",
        sha256="abc123sha",
        status="indexed",
        page_count=5,
        chunk_count=10,
    )
    db.add(doc_a)
    db.commit()

    # User B gets an auth token
    token_b = create_access_token(user_id=user_b.id, email=user_b.email, role="student")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B tries to delete User A's document
    resp = client.delete(f"/documents/{doc_a.id}", headers=headers_b)
    assert resp.status_code == 404, f"Expected 404 but got {resp.status_code}"

    # Verify document still exists in DB
    check_doc = db.query(Document).filter(Document.id == doc_a.id).first()
    assert check_doc is not None, "User A's document must not be deleted by User B"


def test_user_b_cannot_list_user_a_documents(client, db):
    """User B's document list must NEVER show User A's documents."""
    user_a = _create_user(db, "user_a_list@test.com", "user-a-list")
    user_b = _create_user(db, "user_b_list@test.com", "user-b-list")

    doc_a = Document(
        id="doc-a-list",
        user_id=user_a.id,
        filename="user_a_private.pdf",
        sha256="hash-a",
        status="indexed",
    )
    doc_b = Document(
        id="doc-b-list",
        user_id=user_b.id,
        filename="user_b_public.pdf",
        sha256="hash-b",
        status="indexed",
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    token_b = create_access_token(user_id=user_b.id, email=user_b.email, role="student")
    resp_b = client.get("/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.status_code == 200
    docs_b = resp_b.json()["documents"]

    doc_ids_b = [d["id"] for d in docs_b]
    assert "doc-b-list" in doc_ids_b
    assert "doc-a-list" not in doc_ids_b, "User A's document leaked to User B"


def test_user_b_scoped_retrieval_isolation(db):
    """
    Retrieval query must filter by WHERE user_id = ...
    User B must NEVER retrieve chunks belonging to User A.
    """
    user_a_id = "user-isolation-a"
    user_b_id = "user-isolation-b"

    doc_a = Document(
        id="doc-iso-a",
        user_id=user_a_id,
        filename="classified.pdf",
        sha256="hash-iso-a",
        status="indexed",
        source_type="pdf",
    )
    doc_b = Document(
        id="doc-iso-b",
        user_id=user_b_id,
        filename="baking.pdf",
        sha256="hash-iso-b",
        status="indexed",
        source_type="pdf",
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    chunk_a = Chunk(
        document_id=doc_a.id,
        user_id=user_a_id,
        page=1,
        text="The nuclear launch codes are 0000-1111-2222.",
    )
    chunk_b = Chunk(
        document_id=doc_b.id,
        user_id=user_b_id,
        page=1,
        text="The recipe for chocolate chip cookies uses flour and butter.",
    )
    db.add_all([chunk_a, chunk_b])
    db.commit()

    # Query as User B
    results_for_b = search(
        query="nuclear launch codes",
        user_id=user_b_id,
        db=db,
        k=5,
    )

    retrieved_texts = [c.page_content for c in results_for_b]
    assert not any("nuclear launch" in t for t in retrieved_texts), "User A's chunk retrieved by User B!"


def test_delete_all_my_data_isolation(client, db):
    """Calling DELETE /me/data only wipes caller's data, leaves other users intact."""
    user_a = _create_user(db, "user_a_wipe@test.com", "user-a-wipe")
    user_b = _create_user(db, "user_b_wipe@test.com", "user-b-wipe")

    doc_a = Document(
        id="doc-a-survive",
        user_id=user_a.id,
        filename="user_a_permanent.pdf",
        sha256="hash-survive",
        status="indexed",
    )
    doc_b = Document(
        id="doc-b-delete",
        user_id=user_b.id,
        filename="user_b_temp.pdf",
        sha256="hash-delete",
        status="indexed",
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    # User B calls /me/data
    token_b = create_access_token(user_id=user_b.id, email=user_b.email, role="student")
    resp = client.delete("/me/data", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 200

    # User B has no docs
    docs_b_remaining = db.query(Document).filter(Document.user_id == user_b.id).count()
    assert docs_b_remaining == 0

    # User A's doc is untouched
    docs_a_remaining = db.query(Document).filter(Document.user_id == user_a.id).count()
    assert docs_a_remaining == 1
