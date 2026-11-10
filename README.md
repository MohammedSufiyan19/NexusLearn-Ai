# NexusLearn AI 🎓 (v2.0)

**Measured, Multi-User, and Secure Academic RAG System**

NexusLearn AI transforms personal study materials into an isolated, cited, and prompt-injection-resistant academic assistant. Students upload notes, slides, and exam papers to receive grounded answers referencing exact files and page numbers.

[![CI Pipeline](https://github.com/MS-CONQUEROR/NexusLearn-Ai/actions/workflows/ci.yml/badge.svg)](https://github.com/MS-CONQUEROR/NexusLearn-Ai/actions)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel-blue?style=for-the-badge)](https://nexuslearn-ai.vercel.app)
[![API Docs](https://img.shields.io/badge/API%20Docs-FastAPI-emerald?style=for-the-badge)](http://localhost:8000/docs)
[![Security Suite](https://img.shields.io/badge/Prompt%20Injection-ASR%20Reduction%2053.6%25-red?style=for-the-badge)](security/README.md)

---

## 🌟 What Makes NexusLearn v2.0 Distinctive

Most RAG prototypes share a single vector index across all users, lack authentication, and fall victim to indirect prompt injection. NexusLearn v2.0 is built on **measurable evidence, tenant isolation, and defence-in-depth**:

1. **Strict Multi-User Isolation:** Per-user query scoping (`WHERE user_id = ...`) in PostgreSQL + pgvector (or SQLite local dev). User B cannot retrieve, list, or delete User A's data (OWASP BOLA IDOR prevention returning 404).
2. **Empirical Prompt Injection Defence:** Built-in heuristic chunk filtering, `<study_material>` delimiter encapsulation, and output sanitization eliminating markdown image exfiltration (measured 53.6% reduction in Attack Success Rate across 28 test cases).
3. **Honest LLM Resilience:** Primary Groq (`llama-3.3-70b-versatile`) with exponential backoff and jitter, plus an automated circuit breaker failing over to Mistral Large during provider degradation.
4. **Argon2id & JWT Authentication:** Cryptographically strong password hashing with Argon2id, short-lived JWT access tokens, and server-side tracked refresh tokens with rotation and revocation.
5. **Deterministic & LLM Eval Harness:** Built-in calculation of Hit@k, MRR, and Page Recall@k over a curated 48-question gold benchmark, with optional RAGAS evaluation.

---

## 🏗️ Architecture

```
                                  [ User Request ]
                                         │
                                         ▼
                            ┌────────────────────────┐
                            │   React + Vite Client  │
                            └────────────┬───────────┘
                                         │ Bearer JWT
                                         ▼
                       ┌──────────────────────────────────┐
                       │      FastAPI Security Layer      │
                       │  • Security Headers (OWASP)      │
                       │  • Strict CORS Validation        │
                       │  • JWT Auth & Argon2 Verification│
                       └─────────────────┬────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
      ┌─────────────────────┐                         ┌─────────────────────┐
      │   Document Router   │                         │     Chat Router     │
      │ • Magic Byte Check  │                         │ • Scoped Retrieval  │
      │ • Zip-Bomb Defense  │                         │ • Cache Check (ans:)│
      │ • Background Chunk  │                         │ • Rate Limiting     │
      └──────────┬──────────┘                         └──────────┬──────────┘
                 │                                               │
                 ▼                                               ▼
  ┌───────────────────────────────┐               ┌───────────────────────────────┐
  │ Storage & Persistence Layer   │               │ RAG Generator & LLM Engine   │
  │ • PostgreSQL + pgvector       │◄──────────────┤ • Suspicious Chunk Sanitizer  │
  │ • SQLite (Dev/Test Fallback)  │  Dense/BM25   │ • XML Delimiter Wrapping      │
  │ • Redis Caching (User Scoped) │               │ • Groq Primary / Mistral Fall │
  │ • Audit Log Table             │               │ • Image URL Exfil Filter      │
  └───────────────────────────────┘               └───────────────────────────────┘
```

---

## 🛠️ The 4 Agent Tools

| Tool | Trigger | Functionality |
|------|---------|---------------|
| **Topic Explainer** | Conceptual queries | Structured theory, bullet-point concepts, and examples from documents |
| **Question Solver** | Exam problems & code | Step-by-step reasoning with exact formula derivations and citations |
| **Learning Path Generator** | Preparation requests | Realistic day-wise schedule prioritized by syllabus weightage |
| **Content Synthesizer** | Multi-topic queries | Cross-references notes, slide decks, and textbooks into unified summaries |

---

## 🛡️ Security & Prompt Injection Benchmark

NexusLearn includes a reproducible 28-attack red-teaming benchmark (`security/`):

| Attack Category | Cases | Naive ASR (No Defence) | Defended ASR (NexusLearn) | Impact |
|-----------------|-------|------------------------|---------------------------|--------|
| **Direct Override** | 4 | 100.0% | 50.0% | **-50.0%** |
| **System Prompt Extraction** | 4 | 0.0% | 0.0% | **0.0% (Secured)** |
| **Data Exfiltration (Images/Links)** | 4 | 100.0% | 0.0% | **-100.0% (Eliminated)** |
| **Role-Play / Jailbreak** | 4 | 100.0% | 25.0% | **-75.0%** |
| **Hidden Text / Metadata** | 4 | 100.0% | 50.0% | **-50.0%** |
| **Instruction Split** | 4 | 50.0% | 0.0% | **-50.0%** |
| **Cross-Document Contradiction** | 4 | 100.0% | 50.0% | **-50.0%** |
| **OVERALL TOTAL** | **28** | **78.6%** | **25.0%** | **-53.6% Drop** |

Run the injection benchmark:
```bash
python -m security.run_attacks
```

---

## ⚡ Quick Start & Installation

### Option 1: Docker Compose (Recommended)

Run the entire stack locally with PostgreSQL 16 (pgvector pre-installed), Redis 7, and FastAPI:

```bash
# 1. Clone repository
git clone https://github.com/MS-CONQUEROR/NexusLearn-Ai.git
cd NexusLearn-Ai

# 2. Copy environment template
cp .env.example .env
# Fill in GROQ_API_KEY and MISTRAL_API_KEY in .env

# 3. Launch stack
docker-compose up -d --build
```
API docs will be available at `http://localhost:8000/docs`.

---

### Option 2: Local Python Environment

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-eval.txt

# 3. Configure .env
cp .env.example .env

# 4. Start backend
uvicorn main:app --app-dir backend --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testing & Evaluation

```bash
# Run full pytest test suite (19 tests covering Auth, Isolation, Cache, Circuit Breaker, Loaders)
pytest backend/tests/ -v

# Run the 28-attack prompt injection suite
python -m security.run_attacks

# Run retrieval evaluation against gold benchmark
python -m eval.run --config baseline

# Code quality check with Ruff
ruff check backend/ eval/ security/
```

---

## 📁 Repository Layout

```
NexusLearn-Ai/
├── backend/
│   ├── app/
│   │   ├── api/            # Routers: auth, documents, chat, health
│   │   ├── audit/          # Security audit logger
│   │   ├── cache/          # Redis caching (user-scoped) & rate limiting
│   │   ├── core/           # Config, security (Argon2/JWT), FastAPI dependencies
│   │   ├── db/             # SQLAlchemy models, session engine (PostgreSQL/SQLite)
│   │   ├── llm/            # Circuit breaker, exponential backoff, providers
│   │   └── rag/            # Magic-byte loaders, hybrid retriever, prompt generator
│   ├── tests/              # Pytest suite: isolation, auth, circuit breaker, loaders
│   └── main.py             # FastAPI entry point & security headers middleware
├── eval/
│   ├── gold.jsonl          # 48 verified ground-truth benchmark questions
│   ├── metrics.py          # Hit@k, MRR, Page Recall@k
│   └── run.py              # Baseline eval runner & RAGAS integration
├── security/
│   ├── injection_cases/    # 28 prompt injection attack definitions
│   ├── run_attacks.py      # Empirical ASR evaluation script
│   └── README.md           # Security documentation & threat model
├── frontend/               # React + Vite application
├── Dockerfile              # Backend container definition
├── docker-compose.yml      # Local multi-container orchestration
├── .github/workflows/ci.yml # Automated CI pipeline
├── requirements.txt        # Production dependencies
└── requirements-eval.txt   # Evaluation & testing dependencies
```
