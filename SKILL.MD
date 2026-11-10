Claude


Nexuslearn upgrade roadmap · MD
NexusLearn AI: Upgrade Roadmap
Goal: turn NexusLearn from "a RAG demo" into a measured, multi-user, secure system with evidence (numbers, tests, a write-up). Why: RAG-over-PDF is a crowded category (NotebookLM, ChatGPT/Claude projects, hundreds of repos). You will not win on features. You win on proof: eval numbers, an ablation table, an isolation test, and an injection test suite.

0. Ground rules
Measure before you build. Phase 1 (eval harness) comes first, so every later change has a before/after number.
One change per experiment. Never change chunking, retriever and prompt at once.
No claim without evidence. "Faster", "more accurate", "secure" each need a number or a test in the repo.
Cut scope early. Anything marked Optional is skipped if you are short on time.
1. Current state and known weaknesses (from the repo)
Area	Today	Problem
Vector store	Single global FAISS index, in memory	All users share all documents. /clear deletes everyone's data. Index is lost on every Railway redeploy.
Auth	None	Anyone with the URL can upload, query, and clear.
Retrieval	Dense only, top-5, 1000/200 chunks	No hybrid, no rerank, no evidence it works.
LLM layer	Groq primary, Mistral fallback, 5-key rotation	Groq limits apply per organization, so extra keys from one org add no capacity. See Phase 6.
Eval	None	The report has empty RAGAS cells.
Security	Env-var keys only	No upload validation, no prompt-injection defence, no audit log.
Ops	Manual deploy	No tests, no CI, no Docker.
Fix order matters: isolation and persistence (Phase 2) must exist before auth (Phase 3) is meaningful.

2. Phase plan (suggested order and time)
Phase	What	Time	Output you can show
1	Eval harness (gold set, retrieval metrics, RAGAS)	3 to 4 days	Baseline numbers
2	Persistence and per-user isolation (Postgres + pgvector)	3 to 4 days	Isolation test passing
3	Authentication and authorization	2 to 3 days	Login, JWT, ownership checks
4	Retrieval upgrade (hybrid, rerank, tuning)	3 to 4 days	Ablation table
5	Redis (cache, rate limit, jobs)	2 to 3 days	Latency and cost before/after
6	LLM layer cleanup and resilience	1 day	Honest fallback design
7	Security hardening and injection tests	3 to 4 days	Attack suite + results
8	Observability, tests, CI, Docker	2 to 3 days	Green CI badge
9	Write-up and README	2 days	Blog post, report tables
Total is about 4 to 5 weeks part-time. If you only have 2 weeks, do 1, 2, 3, 4 and the isolation and injection tests from 7.

Phase 1: Evaluation harness (do this first)
1.1 Build a gold set
Pick 3 to 5 real documents (a textbook chapter, lecture notes, a past paper, a PPTX).
Write 40 to 60 questions across your four tools (explain, solve, plan, synthesize) plus 5 to 8 unanswerable questions (answer is not in the documents).
For each question store: question, reference_answer (short, written or verified by you), gold_source (file + page numbers), type.
You may draft questions with an LLM, but you must verify every reference answer by hand. An unreviewed synthetic gold set makes your scores meaningless.
File: eval/gold.jsonl

json
{"id":"q001","question":"What is 2NF?","reference":"A relation is in 2NF if it is in 1NF and has no partial dependency of a non-key attribute on part of a candidate key.","gold_source":[{"file":"dbms_notes.pdf","pages":[12,13]}],"type":"explain"}
1.2 Cheap retrieval metrics first (no LLM needed)
Because you store file + page metadata, you can measure retrieval directly:

Hit@k: is any gold page in the top-k chunks?
MRR: reciprocal rank of the first gold chunk.
Page recall@k.
These are free, deterministic, and fast. Report them alongside RAGAS.

1.3 RAGAS
Latest release I found referenced is ragas 0.4.3 (verify with pip index versions ragas). Pin the exact version in requirements-eval.txt, because metric classes and imports change between releases.
Use the modern API: from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ... Old ragas.metrics imports still load but warn. Note ResponseRelevancy in older tutorials is exported as AnswerRelevancy in the collections API.
Dataset fields: user_input, retrieved_contexts, response, reference.
Metrics to report: faithfulness, answer relevancy, context precision, context recall.
python
# eval/run_ragas.py  (sketch: check signatures against the pinned version's docs)
import json, statistics
from ragas.metrics.collections import Faithfulness, AnswerRelevancy

def run(system, gold_path="eval/gold.jsonl"):
    rows = [json.loads(l) for l in open(gold_path)]
    results = []
    for r in rows:
        out = system.answer(r["question"])   # must return answer + retrieved chunks
        results.append({
            "id": r["id"],
            "user_input": r["question"],
            "retrieved_contexts": [c.text for c in out.chunks],
            "response": out.answer,
            "reference": r["reference"],
            "retrieved_pages": [(c.file, c.page) for c in out.chunks],
        })
    return results   # then score with metric.ascore(...) per row
1.4 Pitfalls (read these)
Judge bias: do not use the same model as both generator and judge. If Groq Llama generates, judge with Mistral Large (or the reverse). State which judge you used in the report.
Judge rate limits: RAGAS makes many LLM calls per row. Throttle concurrency, cache judge outputs to disk, and expect to hit free-tier limits.
Noise: LLM judges are non-deterministic. Run 3 times and report mean ± std. Do not claim a 0.02 improvement.
Unanswerable questions: score separately. The correct behaviour is "not in your material", and a high faithfulness score can hide hallucinated refusals.
Cost: log tokens and rupees per eval run.
1.5 Deliverable
eval/results/baseline.json plus a markdown table:

Config	Hit@5	MRR	Faithfulness	Ans. Relevancy	Ctx Precision	Ctx Recall	p50 latency
Baseline (FAISS top-5)							
Done when: one command (python -m eval.run --config baseline) reproduces the table.

Phase 2: Persistence and per-user isolation
Decision: replace FAISS with Postgres + pgvector
You already know PostgreSQL. One database gives you users, documents, chunks, embeddings, chat history, and audit logs.
Per-user filtering is a plain WHERE user_id = .... With a global FAISS index, isolation is hard and a bug leaks data.
Railway offers Postgres; confirm pgvector support on your plan before committing. Fallback: Supabase or Neon Postgres (both support pgvector).
Keep FAISS as an eval baseline only if you want to compare.
Schema (starting point)
sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|indexed|failed
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, sha256)
);

CREATE TABLE chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,                   -- denormalised for fast filtering
  page INT,
  text TEXT NOT NULL,
  embedding vector(1024)                   -- match your Mistral embed dimension; verify
);
CREATE INDEX ON chunks (user_id);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
Also add chat_sessions, messages, and audit_log tables (see Phases 3 and 7).

Isolation test (the most important test in the repo)
python
def test_user_b_cannot_retrieve_user_a_chunks(client, user_a, user_b):
    upload(client, user_a, "secret_notes.pdf")
    r = chat(client, user_b, "What does secret_notes say about X?")
    assert "secret_notes" not in str(r.sources)
    assert r.status_code == 200 and r.sources == []
Also test: user B cannot DELETE user A's document (expect 404, not 403, to avoid leaking existence), and /clear only clears the caller's data.

Done when: two users can upload different files, never see each other's content, and data survives a redeploy.

Phase 3: Authentication and authorization
Authentication = who are you. Authorization = what may you touch. Do both.

3.1 Choose
Build it yourself (good for learning, fine for a student project): email + password, JWT access token, refresh token.
Or use a provider (Clerk, Supabase Auth, Auth0, Google sign-in): less code, fewer ways to get it wrong. For a portfolio, a Google/GitHub OAuth login is often enough and safer than rolling your own.
If you build it yourself:

Hash with Argon2 (e.g. argon2-cffi or pwdlib). Do not use plain SHA/MD5, and note passlib is largely unmaintained.
Use a maintained JWT library (PyJWT). Short-lived access tokens (about 15 minutes), longer refresh tokens stored server-side so they can be revoked.
Put the signing secret in env vars, never in git.
Validate exp, iss, and aud. Pin the algorithm (do not accept alg: none).
3.2 Authorization rules
Every route takes current_user = Depends(get_current_user).
Every query that touches documents, chunks, chats, or deletes includes user_id = current_user.id. Never trust a document_id from the client without an ownership check (this is the classic IDOR bug).
Roles (keep it small): student, admin. Admin can view usage stats, not other users' content.
Quotas per user: max files, max total MB, max requests/day.
3.3 Routes after the change
Method	Route	Auth	Notes
POST	/auth/register, /auth/login, /auth/refresh	no	Rate limit hard
POST	/documents	yes	Validate file (Phase 7)
GET	/documents	yes	Only own
DELETE	/documents/{id}	yes	Ownership check, 404 if not owner
POST	/chat	yes	Scoped retrieval
DELETE	/me/data	yes	Replaces global /clear
3.4 Tests
No token gives 401. Expired token gives 401. Tampered token gives 401.
User B accessing user A's document id gives 404.
Brute-force login attempts are rate limited (Phase 5).
Done when: the OWASP API Top 10 item "Broken Object Level Authorization" is covered by an automated test.

Phase 4: Retrieval upgrade (with ablation)
Run each experiment through the Phase 1 harness. Change one thing at a time.

#	Experiment	Expected effect	Cost
A	Baseline: dense top-5	n/a	n/a
B	Chunk size sweep: 500 / 800 / 1000 / 1500, overlap 10 to 20%	Precision vs. recall trade-off	Re-embed
C	Hybrid: BM25 + dense, fuse with Reciprocal Rank Fusion	Helps exact terms (acronyms, formulas, "Q3")	Low
D	Cross-encoder reranker (retrieve 20, rerank to 5)	Better precision	Adds latency
E	Query rewriting or multi-query	Helps vague queries	Extra LLM call
F	Better parsing (keep tables, headings; page-aware chunks)	Helps PDFs with tables	Medium
Notes:

With Postgres you can do BM25-like search with tsvector full-text search, or use a Python BM25 library for the prototype.
Rerankers: try a small open cross-encoder first (runs on CPU) and measure latency honestly. A slow reranker may not be worth it on free-tier hosting.
Keep an eval/results/ablation.md table, and keep the experiments that did not help. Negative results are credible evidence.
Done when: you can state, with numbers, which change helped most and what it cost in latency.

Phase 5: Redis (use it where it pays)
Red-team note: do not add Redis just to list it on a resume. Add it only for the four jobs below, and measure each.

Use	How	Measure
Embedding cache	Key emb:{sha256(text)}, no TTL or long TTL	Fewer embed API calls on re-uploads
Query/answer cache	Key ans:{user_id}:{doc_set_version}:{sha256(normalized_question)}, TTL 1 hour, invalidate when the user's documents change	Cache hit rate, p50 latency, API cost saved
Rate limiting	INCR + EXPIRE per user_id or IP (or a library such as slowapi / fastapi-limiter)	429s under load test
Background jobs	Queue ingestion (parse, chunk, embed) so /documents returns immediately with status=pending	Upload response time
Pitfalls:

Cache poisoning and leakage: include user_id and a document-set version in every answer-cache key, or one user can receive another's cached answer. Add a test for this.
Do not cache answers to unanswerable or error cases for long.
Redis is a cache, not the source of truth. The app must work (slower) if Redis is down.
Railway provides a Redis service template; check current pricing and memory limits before relying on it. Set maxmemory and an eviction policy.
For the job queue, start with FastAPI BackgroundTasks. Move to a real queue (ARQ, RQ, or Celery) only if you need retries and persistence.
Done when: you can show a before/after table: p50/p95 latency, cache hit rate, and API calls per 100 queries.

Phase 6: LLM layer cleanup and resilience
Fix the key-rotation claim
Groq's docs state rate limits apply at the organization level, not per key or per user. Five keys from one organization therefore share one quota. If the five keys come from five separate accounts, that is working around the limits and may violate Groq's terms; read them before doing it. Remove the "5 keys rotating, zero downtime" claim from the README, report, and code comments.

Replace with honest resilience
One Groq key, with retry + exponential backoff + jitter, honouring the retry-after header on 429.
Circuit breaker: after N consecutive failures, route to Mistral for a cooldown window, then probe Groq again.
Timeouts on every external call.
Log which provider answered each request (needed for eval and cost tracking).
Consider a small paid budget or the provider's higher tier if you need real throughput. State the limits you actually have.
Streaming (nice UX win)
Stream tokens to the React UI with Server-Sent Events. Measure time-to-first-token, which is what users feel.

Done when: a simulated 429 from the primary results in a correct answer from the fallback, covered by a test (this is report test case TC5).

Phase 7: Security hardening (ties to your AI-security goal)
This is the phase that makes the project distinctive for AI-security roles.

7.1 Upload safety
Allowlist types by content (magic bytes), not just extension.
Max file size, max pages, max total per user. DOCX and PPTX are zip files, so guard against zip bombs (limit uncompressed size and entry count).
Parse with a timeout. Never execute or render macros.
Store files outside the web root, with random names. Compute and store SHA-256.
Optional: virus scan (ClamAV) for a "production-style" claim.
7.2 Indirect prompt injection (the key threat for RAG)
Uploaded documents are untrusted input. A PDF can contain text like "ignore previous instructions and ...".

Defences (layer them, none is sufficient alone):

Put retrieved text inside clear delimiters and instruct the model to treat it as data, not instructions.
The generator has no tools with side effects (no email, no file write, no network).
Strip or neutralize suspicious patterns; flag chunks that look like instructions.
Output filtering: block or neutralize external URLs and markdown images in answers (markdown image URLs are a known data-exfiltration channel). In React, do not auto-load remote images from model output.
Keep system prompts free of secrets.
7.3 Build an injection test suite (your portfolio centrepiece)
Create security/injection_cases/ with 25 to 40 poisoned documents:

Direct instruction override in a chunk.
Hidden text (white-on-white, tiny font, metadata fields).
Instruction split across two chunks.
Exfiltration attempt via markdown image or link.
Attempt to make the model reveal the system prompt.
Cross-document attack (poisoned file tries to affect answers about a different file).
Report an attack success rate before and after each defence. Tools you can compare against (verify current status before citing): Promptfoo and garak for LLM red-teaming. Keep your own cases small and reproducible.

7.4 API security
CORS: allow only your frontend origin, not *.
Security headers, HTTPS only, secrets only in env vars, rotate any key ever committed.
Input length limits on /chat. Never log raw document text or full prompts at INFO level.
Dependency scanning (pip-audit, Dependabot) and secret scanning (GitHub secret scanning, gitleaks).
7.5 Audit log
Table audit_log(id, user_id, action, resource, ip, user_agent, ts, outcome). Log: login success/fail, upload, delete, chat (metadata only), authorization denials. This feeds directly into your future MCP/agent gateway idea.

Done when: security/README.md shows a table of attacks, defences, and measured success rates, reproducible with one command.

Phase 8: Observability, testing, CI, Docker
LangSmith traces (you already know it): tag by user (hashed), provider, cache hit, latency.
Structured JSON logs with a request id.
Metrics to track: p50/p95 latency, error rate, cache hit rate, tokens and rupees per query, fallback rate.
Tests (pytest): loaders (PDF/DOCX/PPTX fixtures), chunking, retrieval hit@k on a tiny fixture set, auth, isolation, rate limit, cache keys, fallback.
CI (GitHub Actions): lint (ruff), tests, pip-audit. Add a small eval smoke test (5 to 10 questions) that fails the build if hit@5 or faithfulness drops below a threshold. Do not run the full RAGAS suite on every push; it is slow and costs money.
Docker: Dockerfile for backend, docker-compose.yml for backend + Postgres + Redis, so anyone can run it with one command. Add a .env.example.
Fix the README: correct repo URL, correct install path (requirements.txt is in the repo root), remove the key-rotation claim.
Phase 9: Write-up (what gets you interviews)
README: architecture diagram, what is measured, how to reproduce eval and attacks.
Blog post / report section: "What I measured when I upgraded a student RAG app": the ablation table, the injection results, the isolation bug you found and fixed.
Report tables: fill Table 7.2 only with measured configurations. Delete rows for features you did not build.
Short demo video (2 minutes).
Post the injection suite as a standalone repo. This is your path to conversations with people working in AI security.
Suggested repo layout
nexuslearn/
  backend/
    app/
      api/            # routers: auth, documents, chat
      core/           # config, security, deps
      db/             # models, migrations (alembic)
      rag/            # loaders, chunking, retriever, reranker, generator
      llm/            # providers, retry, circuit breaker
      cache/          # redis helpers
      audit/
    tests/
  eval/
    gold.jsonl
    run.py
    results/
  security/
    injection_cases/
    run_attacks.py
    README.md
  frontend/
  docker-compose.yml
  .github/workflows/ci.yml
  requirements.txt
  requirements-eval.txt
What NOT to do
Do not add Kubernetes, microservices, or vector DBs you do not need. Postgres + Redis is plenty.
Do not add more "agent tools" (flashcards, quizzes) before eval and security exist. Features are the crowded part.
Do not publish RAGAS scores from an unreviewed or tiny gold set, or with the generator as its own judge.
Do not claim "production-grade", "secure", or "zero downtime" anywhere without a test or measurement backing it.
Do not roll your own crypto, and never commit .env.
Definition of done (portfolio-ready)
 One-command eval reproduces the baseline and best-config tables
 Ablation table includes at least 4 configurations, with mean ± std
 Two-user isolation and ownership tests pass in CI
 Login works (own JWT or OAuth provider), all routes protected
 Redis caching, rate limiting, and ingestion queue measured before/after
 Injection suite (25+ cases) with before/after attack success rates
 Audit log in place
 Docker compose runs the whole stack locally
 README accurate (correct URLs, no unverified claims)
 Blog post or report section published
Reading list
Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (RAG)
Es et al., RAGAs: Automated Evaluation of Retrieval Augmented Generation
Greshake et al., Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection
OWASP Top 10 for LLM Applications; OWASP API Security Top 10
RAGAS docs (pin the version you install), pgvector README, FastAPI security tutorial
Groq rate-limits docs (organization-level limits, retry-after header)
Verify before you rely on it
Items I could not confirm and you should check yourself: current latest ragas version and exact metric signatures; pgvector availability on your Railway plan; Mistral embedding dimension for your vector(N) column; Railway Redis pricing and limits; current status and licenses of Promptfoo and garak.





Claude finished the response
