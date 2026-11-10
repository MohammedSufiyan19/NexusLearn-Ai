"""
NexusLearn AI — Retriever
Unified retrieval layer supporting:
  - FAISS (local dev, no DB)
  - PostgreSQL + pgvector (production, dense search)
  - BM25 hybrid fusion via Reciprocal Rank Fusion (Phase 4)
"""
import json
import logging
import math

from app.cache.redis_client import get_cached_embedding, set_cached_embedding
from app.core.config import settings
from app.llm.providers import get_embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# ── Text Splitter ─────────────────────────────────────────────────────────────

def get_splitter(chunk_size: int = None, chunk_overlap: int = None) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.default_chunk_size,
        chunk_overlap=chunk_overlap or settings.default_chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


# ── Embedding with Cache ──────────────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    """Embed a single text string, using Redis cache if available."""
    cached = get_cached_embedding(text)
    if cached:
        return cached
    embeddings = get_embeddings()
    vec = embeddings.embed_query(text)
    set_cached_embedding(text, vec)
    return vec


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts, using Redis cache where possible."""
    results = []
    to_embed = []
    indices_needing_embed = []

    for i, text in enumerate(texts):
        cached = get_cached_embedding(text)
        if cached:
            results.append(cached)
        else:
            results.append(None)
            to_embed.append(text)
            indices_needing_embed.append(i)

    if to_embed:
        embeddings = get_embeddings()
        vecs = embeddings.embed_documents(to_embed)
        for idx, vec in zip(indices_needing_embed, vecs):
            results[idx] = vec
            set_cached_embedding(texts[idx], vec)

    return results


# ── BM25 (Keyword) Retrieval ──────────────────────────────────────────────────

class BM25Index:
    """
    Minimal in-memory BM25 index for a list of Document objects.
    Used as the keyword leg of hybrid retrieval.
    """
    def __init__(self, docs: list[Document], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self._build(docs)

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def _build(self, docs: list[Document]):
        from collections import Counter
        self.doc_freqs = []
        self.idf = {}
        self.avgdl = 0.0
        N = len(docs)

        df_counter = Counter()
        for doc in docs:
            tokens = set(self._tokenize(doc.page_content))
            df_counter.update(tokens)
            self.doc_freqs.append(Counter(self._tokenize(doc.page_content)))

        self.avgdl = sum(len(self._tokenize(d.page_content)) for d in docs) / max(N, 1)

        for term, df in df_counter.items():
            self.idf[term] = math.log((N - df + 0.5) / (df + 0.5) + 1)

    def score(self, query: str) -> list[float]:
        tokens = self._tokenize(query)
        scores = []
        for tf in self.doc_freqs:
            dl = sum(tf.values())
            s = 0.0
            for t in tokens:
                if t not in tf:
                    continue
                idf = self.idf.get(t, 0.0)
                freq = tf[t]
                s += idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            scores.append(s)
        return scores

    def get_top_k(self, query: str, k: int) -> list[Document]:
        scores = self.score(query)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self.docs[i] for i in ranked[:k]]


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_docs: list[Document],
    sparse_docs: list[Document],
    k: int = 60,
    top_n: int = 5,
) -> list[Document]:
    """
    Fuse two ranked lists using RRF.
    Returns top_n deduplicated documents.
    """
    scores = {}
    doc_map = {}

    for rank, doc in enumerate(dense_docs):
        key = doc.page_content[:100]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        doc_map[key] = doc

    for rank, doc in enumerate(sparse_docs):
        key = doc.page_content[:100]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        doc_map[key] = doc

    sorted_keys = sorted(scores.keys(), key=lambda k_: scores[k_], reverse=True)
    return [doc_map[key] for key in sorted_keys[:top_n]]


# ── FAISS Retriever (local dev) ───────────────────────────────────────────────

_faiss_store = None  # module-level singleton


def _get_faiss_store():
    global _faiss_store
    if _faiss_store is not None:
        return _faiss_store
    try:
        import os

        from langchain_community.vectorstores import FAISS
        faiss_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "vectorstore", "faiss_index")
        faiss_path = os.path.abspath(faiss_path)
        if os.path.exists(faiss_path):
            emb = get_embeddings()
            _faiss_store = FAISS.load_local(faiss_path, emb, allow_dangerous_deserialization=True)
    except Exception as exc:
        logger.debug("FAISS load failed: %s", exc)
    return _faiss_store


# ── pgvector Retriever (production) ──────────────────────────────────────────

def _pgvector_search(query: str, user_id: str, db, k: int) -> list[Document]:
    """Dense vector search via pgvector, scoped to user."""

    from sqlalchemy import text as sa_text

    query_vec = embed_text(query)
    vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

    # Use pgvector cosine similarity operator <=>
    sql = sa_text("""
        SELECT c.text, c.page, d.filename, d.source_type, d.id as doc_id,
               (c.embedding <=> :vec::vector) AS distance
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.user_id = :uid AND d.status = 'indexed'
        ORDER BY c.embedding <=> :vec::vector
        LIMIT :k
    """)

    try:
        rows = db.execute(sql, {"vec": vec_str, "uid": str(user_id), "k": k}).fetchall()
        return [
            Document(
                page_content=row.text,
                metadata={
                    "source": row.filename,
                    "page": row.page,
                    "source_type": row.source_type,
                    "document_id": str(row.doc_id),
                }
            )
            for row in rows
        ]
    except Exception as exc:
        logger.error("pgvector search failed: %s", exc)
        return []


def _sqlite_search(query: str, user_id: str, db, k: int) -> list[Document]:
    """Fallback keyword search for SQLite (no pgvector)."""
    from app.db.models import Chunk
    from app.db.models import Document as DocModel
    chunks = (
        db.query(Chunk)
        .join(DocModel, Chunk.document_id == DocModel.id)
        .filter(Chunk.user_id == str(user_id), DocModel.status == "indexed")
        .all()
    )
    if not chunks:
        return []
    docs = [
        Document(
            page_content=c.text,
            metadata={"source": c.document.filename, "page": c.page,
                      "source_type": c.document.source_type}
        )
        for c in chunks
    ]
    bm25 = BM25Index(docs)
    return bm25.get_top_k(query, k)


# ── Public Search Interface ───────────────────────────────────────────────────

def search(
    query: str,
    user_id: str | None = None,
    db=None,
    k: int = None,
    use_hybrid: bool = True,
) -> list[Document]:
    """
    Unified search: chooses backend based on what's configured.
      - PostgreSQL + pgvector: dense + BM25 hybrid with RRF
      - SQLite: BM25 only
      - No DB (FAISS mode): dense only from FAISS index
    Always scoped to user_id when db is provided.
    """
    k = k or settings.default_top_k
    fetch_k = settings.rerank_top_n  # fetch more, then fuse/rerank

    # ── Postgres + pgvector ─────────────────────────────────────────────────
    if db is not None and settings.database_url.startswith("postgresql"):
        dense = _pgvector_search(query, user_id, db, fetch_k)
        if use_hybrid and dense:
            bm25 = BM25Index(dense)
            sparse = bm25.get_top_k(query, fetch_k)
            return reciprocal_rank_fusion(dense, sparse, top_n=k)
        return dense[:k]

    # ── SQLite fallback ─────────────────────────────────────────────────────
    if db is not None:
        return _sqlite_search(query, user_id, db, k)

    # ── FAISS (local dev, no DB) ────────────────────────────────────────────
    store = _get_faiss_store()
    if store:
        return store.similarity_search(query, k=k)

    logger.warning("No retrieval backend available — returning empty results")
    return []


# ── Index New Chunks ──────────────────────────────────────────────────────────

def index_document(docs: list[Document], user_id: str, document_id: str, db=None) -> int:
    """
    Chunk, embed, and store documents.
    Returns number of chunks indexed.
    """
    splitter = get_splitter()
    chunks = splitter.split_documents(docs)

    if db is not None:
        # DB mode: store in chunks table
        from app.db.models import Chunk

        if settings.database_url.startswith("postgresql"):
            # pgvector: embed and store vectors
            texts = [c.page_content for c in chunks]
            vectors = embed_documents(texts)

            chunk_objs = []
            for c, vec in zip(chunks, vectors):
                chunk_objs.append(Chunk(
                    document_id=document_id,
                    user_id=str(user_id),
                    page=c.metadata.get("page"),
                    text=c.page_content,
                    embedding_json=json.dumps(vec),  # also store as JSON for migration
                ))
            db.bulk_save_objects(chunk_objs)

            # Insert embeddings into pgvector column
            for chunk_obj, vec in zip(chunk_objs, vectors):
                db.execute(
                    "UPDATE chunks SET embedding = %s::vector WHERE id = %s",
                    ("[" + ",".join(str(v) for v in vec) + "]", chunk_obj.id)
                )
        else:
            # SQLite: store text only (BM25 retrieval)
            chunk_objs = [
                Chunk(
                    document_id=document_id,
                    user_id=str(user_id),
                    page=c.metadata.get("page"),
                    text=c.page_content,
                )
                for c in chunks
            ]
            db.bulk_save_objects(chunk_objs)

        db.commit()
        return len(chunks)

    # FAISS mode (local dev)
    global _faiss_store
    try:
        import os

        from langchain_community.vectorstores import FAISS
        emb = get_embeddings()
        faiss_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "vectorstore", "faiss_index")
        )
        if _faiss_store is not None:
            _faiss_store.add_documents(chunks)
        elif os.path.exists(faiss_path):
            _faiss_store = FAISS.load_local(faiss_path, emb, allow_dangerous_deserialization=True)
            _faiss_store.add_documents(chunks)
        else:
            _faiss_store = FAISS.from_documents(chunks, emb)
        _faiss_store.save_local(faiss_path)
    except Exception as exc:
        logger.error("FAISS indexing failed: %s", exc)

    return len(chunks)
