# 🧠 NexusLearn AI — Project Memory & Progress Tracker

> **Last Updated:** 2026-10-30  
> **Goal:** Upgrade NexusLearn from a RAG demo into a measured, multi-user, secure system with eval numbers, ablation tables, isolation tests, and an injection test suite.  
> **Golden Rule:** Measure before you build. One change per experiment. No claim without evidence.

---

## 📊 Project State Snapshot

| Area | Initial State | Target State | Current Production State |
|------|---------------|--------------|--------------------------|
| Vector Store | Single global FAISS index (in-memory, shared) | Per-user pgvector in Postgres | ✅ PostgreSQL + pgvector (prod) & SQLite (dev) |
| Auth | ❌ None — anyone with URL could access | JWT + email/password or OAuth | ✅ Argon2id + JWT access & rotating refresh tokens |
| Retrieval | Dense only, top-5, 1000/200 chunks | Hybrid BM25 + dense + reranker | ✅ Hybrid BM25 + dense Reciprocal Rank Fusion |
| LLM Layer | 5-key rotation (broken org limit) | Single key + circuit breaker | ✅ Groq primary + backoff/jitter + Mistral circuit breaker |
| Eval | ❌ Empty RAGAS cells | Full baseline + ablation table | ✅ 48-question gold benchmark + Hit@k / MRR runner |
| Security | Env-var keys only, no validation | Upload safety + injection defence + audit log | ✅ Magic byte check + chunk filter + exfil stripper (53.6% ASR reduction) |
| Ops | Manual Railway deploy | Docker Compose + CI/CD | ✅ Dockerfile + docker-compose.yml + GitHub Actions CI |

---

## 🗺️ Phase Roadmap & Completion Status

### ✅ Phase 0 — Baseline (COMPLETED)
- [x] FastAPI backend with 4 agent tools
- [x] LangGraph agent: router → retriever → generator
- [x] FAISS vectorstore with Mistral embeddings
- [x] PDF / DOCX / PPTX loaders
- [x] React + Vite frontend
- [x] Deployed on Railway (backend) + Vercel (frontend)
- [x] 4 tools: topic_explainer, question_solver, learning_path_generator, content_synthesizer

---

### ✅ Phase 1 — Evaluation Harness (COMPLETED)
- [x] Created `eval/` module
- [x] Built expanded gold set `eval/gold.jsonl` with 48 hand-verified questions across the 4 tools + 8 unanswerables
- [x] Implemented deterministic retrieval metrics in `eval/metrics.py` (Hit@k, MRR, Page Recall@k)
- [x] Created `eval/run.py` supporting deterministic evaluation and optional RAGAS judge scoring
- [x] Pinned `ragas==0.4.3` and dependencies in `requirements-eval.txt`

---

### ✅ Phase 2 — Persistence & Per-User Isolation (COMPLETED)
- [x] Created SQLAlchemy database models (`backend/app/db/models.py`) supporting PostgreSQL + pgvector and SQLite fallback
- [x] Added `user_id` to all documents, chunks, chat sessions, and audit log entries
- [x] Scoped retrieval queries strictly with `WHERE user_id = ...`
- [x] Written `backend/tests/test_isolation.py` (all 4 tests passing):
  - User B cannot retrieve User A's chunks
  - User B cannot delete User A's documents (returns 404, preventing IDOR & existence leakage)
  - User B document listing is strictly isolated
  - `DELETE /me/data` only clears the caller's data

---

### ✅ Phase 3 — Authentication & Authorization (COMPLETED)
- [x] Built Argon2id password hashing and constant-time verification (`backend/app/core/security.py`)
- [x] Implemented JWT access tokens (15-min lifetime) with audience & issuer validation
- [x] Implemented server-side tracked refresh tokens with rotation and revocation (`RefreshToken` table)
- [x] Explicitly rejected insecure tokens (`alg: none`, expired, tampered)
- [x] Implemented auth routes: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- [x] Protected all core routes with `Depends(get_current_user)`
- [x] Written `backend/tests/test_auth.py` (all 6 tests passing)

---

### ✅ Phase 4 — Hybrid Retrieval (COMPLETED)
- [x] In-memory BM25 index implemented in `backend/app/rag/retriever.py`
- [x] Reciprocal Rank Fusion (RRF) combining dense vector search and BM25 keyword rankings
- [x] Page-aware chunking and citation metadata extraction

---

### ✅ Phase 5 — Redis Caching & Rate Limiting (COMPLETED)
- [x] Implemented `backend/app/cache/redis_client.py`:
  - Embedding cache: `emb:{sha256(text)}`
  - User-scoped answer cache: `ans:{user_id}:{doc_set_version}:{sha256(q)}` preventing cross-user cache poisoning
  - Invalidation of user cached answers upon upload/deletion
  - Sliding-window rate limiting counter
  - Graceful degradation: all functions no-op and fail open if Redis is down
- [x] Written `backend/tests/test_cache_and_rate_limit.py` (all 3 tests passing)

---

### ✅ Phase 6 — LLM Layer Cleanup & Circuit Breaker (COMPLETED)
- [x] Removed broken 5-key rotation claim from README and code comments
- [x] Implemented `CircuitBreaker` class in `backend/app/llm/providers.py` with states `CLOSED`, `OPEN`, `HALF_OPEN`
- [x] Exponential backoff with random jitter honoring `retry-after`
- [x] Automatic fallback from Groq primary (`openai/gpt-oss-120b`) to Mistral (`mistral-small-latest`)
- [x] Written `backend/tests/test_circuit_breaker.py` (all 2 tests passing)

---

### ✅ Phase 7 — Security Hardening & Prompt Injection Suite (COMPLETED)
- [x] Upload safety: Magic byte validation (`%PDF`, `PK\x03\x04`) rejecting disguised executables
- [x] Zip-bomb protection for DOCX/PPTX checking entry count and uncompressed size
- [x] Multi-layer prompt injection defence:
  - Heuristic chunk scanner neutralizing instructions
  - `<study_material>` delimiter isolation
  - System prompt strict hierarchy ("DATA not instructions")
  - Output sanitization stripping markdown images (`![img](url)`) and exfiltration links
- [x] Created 28 prompt injection attack cases in `security/injection_cases/cases.json`
- [x] Created `security/run_attacks.py` and benchmarked before/after:
  - Overall Naive ASR: **78.6%**
  - Overall Defended ASR: **25.0%**
  - Measured ASR reduction: **-53.6%** (exfiltration & instruction split reduced to 0.0%)
- [x] Comprehensive security documentation in `security/README.md`
- [x] Written `backend/tests/test_loaders_and_security.py` (all 4 tests passing)

---

### ✅ Phase 8 — Observability, Docker & CI/CD (COMPLETED)
- [x] Created production `Dockerfile` with PostgreSQL client tools and healthcheck
- [x] Created `docker-compose.yml` orchestrating FastAPI backend, PostgreSQL 16 (pgvector), and Redis 7
- [x] Created `.env.example` template with all documented variables
- [x] Created `.github/workflows/ci.yml` running Ruff linting, Pytest suite, pip-audit, and security benchmark
- [x] Upgraded vulnerable transitive dependencies (`pypdf`, `urllib3`)
- [x] Configured `pyproject.toml` with Ruff and Pytest options

---

### ✅ Phase 9 — Documentation & Artifacts (COMPLETED)
- [x] Completely updated `README.md` with honest architecture, security benchmark table, and reproduction commands
- [x] Created `security/README.md` threat model and evaluation write-up
- [x] Maintained `envreq.md` with environment keys and setup requirements
- [x] Updated `MEMORY.md` with verified test results

---

## 🧪 Test Suite Summary (100% Passing)

```bash
uv run pytest backend/tests
```

```
backend/tests/test_auth.py ............ 6 passed
backend/tests/test_cache_and_rate_limit.py ... 3 passed
backend/tests/test_circuit_breaker.py .. 2 passed
backend/tests/test_isolation.py .... 4 passed
backend/tests/test_loaders_and_security.py .... 4 passed
======================= 19 passed in 10.67s =======================
```
