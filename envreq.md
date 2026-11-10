# 🔧 NexusLearn AI — Environment Requirements & Keys

> All secrets go in `.env` files **only**. Never commit `.env` to git.  
> A `.env.example` with placeholder values must exist for every `.env`.

---

## 📦 Current .env Keys (Already Set)

| Variable | Service | Where to Get |
|----------|---------|-------------|
| `GROQ_API_KEY` | Groq LLM | https://console.groq.com/keys |
| `GROQ_API_KEY_1` … `GROQ_API_KEY_5` | Groq (same org) | Same page — ⚠️ org-level limits apply |
| `MISTRAL_API_KEY` | Mistral LLM + Embeddings | https://console.mistral.ai/api-keys |
| `GEMINI_API_KEY` | Google Gemini (unused so far) | https://aistudio.google.com/app/apikey |
| `TAVILY_API_KEY` | Tavily web search (unused so far) | https://app.tavily.com/home |

> ⚠️ **Action required:** Run `gitleaks` or GitHub secret scanning to confirm these keys were never committed to git history. Rotate any that were.

---

## 🆕 New Keys & Services Needed Per Phase

### Phase 1 — Eval Harness

| Variable | Service | Where to Get | Notes |
|----------|---------|-------------|-------|
| `OPENAI_API_KEY` *(optional)* | OpenAI — RAGAS judge | https://platform.openai.com/api-keys | Only if using OpenAI as RAGAS judge |
| *(Use existing Mistral key)* | Mistral Large — RAGAS judge | Already set | Recommended: use Mistral as judge when Groq generates |

**Python packages to add to `requirements-eval.txt`:**
```
ragas==<pin exact version — check: pip index versions ragas>
datasets
pandas
numpy
```

---

### Phase 2 — Postgres + pgvector

| Variable | Service | Where to Get | Notes |
|----------|---------|-------------|-------|
| `DATABASE_URL` | PostgreSQL + pgvector | Railway / Supabase / Neon | Format: `postgresql://user:pass@host:5432/dbname` |

**Option A — Railway Postgres:**
- URL: https://railway.app
- Add Postgres service to your project → copy `DATABASE_URL` from Variables tab
- ⚠️ Verify pgvector extension is available on your plan before committing

**Option B — Supabase (free tier, pgvector included):**
- URL: https://supabase.com/dashboard
- Create project → Settings → Database → Connection string (URI)
- Enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;` in SQL editor

**Option C — Neon (free tier, pgvector included):**
- URL: https://console.neon.tech
- Create project → Connection Details → copy connection string

**Python packages to add to `requirements.txt`:**
```
psycopg2-binary
pgvector
alembic
sqlalchemy
asyncpg        # if using async SQLAlchemy
```

---

### Phase 3 — Authentication

#### Option A: Build Your Own JWT Auth
| Variable | Purpose | Notes |
|----------|---------|-------|
| `JWT_SECRET_KEY` | Signing JWT tokens | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_ALGORITHM` | Algorithm (set to `HS256`) | Never use `none` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime (e.g. `15`) | Short-lived |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime (e.g. `7`) | Stored server-side |

**Python packages:**
```
PyJWT
argon2-cffi      # password hashing — do NOT use passlib (largely unmaintained)
python-multipart # for FastAPI form data
```

#### Option B: Clerk (Recommended for portfolio)
- URL: https://dashboard.clerk.com
- Create application → API Keys tab
- Variables needed: `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY` (frontend)
- Docs: https://clerk.com/docs/quickstarts/fastapi

#### Option C: Supabase Auth (if using Supabase for DB)
- Built-in, no extra service needed
- Variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- Docs: https://supabase.com/docs/guides/auth

#### Option D: Auth0
- URL: https://manage.auth0.com
- Variables: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`

---

### Phase 5 — Redis

| Variable | Service | Where to Get | Notes |
|----------|---------|-------------|-------|
| `REDIS_URL` | Redis instance | Railway / Upstash / local | Format: `redis://user:pass@host:6379` |

**Option A — Railway Redis:**
- URL: https://railway.app
- Add Redis service → copy `REDIS_URL` from Variables tab
- ⚠️ Set `maxmemory` and eviction policy (`allkeys-lru` recommended)
- Check current pricing and memory limits before relying on it

**Option B — Upstash Redis (free tier, serverless):**
- URL: https://console.upstash.com
- Create Redis database → copy REST URL and token or Redis connection string
- Good for Railway/Vercel deployments

**Python packages:**
```
redis
fastapi-limiter   # rate limiting
slowapi           # alternative rate limiter
arq               # async job queue (if moving beyond BackgroundTasks)
```

---

### Phase 7 — Security Tools

| Tool | Install | URL | Purpose |
|------|---------|-----|---------|
| `pip-audit` | `pip install pip-audit` | https://pypi.org/project/pip-audit/ | Dependency vulnerability scan |
| `gitleaks` | See docs | https://github.com/gitleaks/gitleaks | Scan git history for secrets |
| `ruff` | `pip install ruff` | https://docs.astral.sh/ruff/ | Fast Python linter for CI |
| Promptfoo | `npm install -g promptfoo` | https://promptfoo.dev | LLM red-teaming (verify license) |
| garak | `pip install garak` | https://github.com/NVIDIA/garak | LLM red-teaming (verify status) |
| ClamAV *(optional)* | System package | https://www.clamav.net | Virus scanning uploaded files |

**GitHub integrations to enable:**
- Dependabot: `.github/dependabot.yml`
- GitHub Secret Scanning: Repository → Settings → Security → Secret scanning
- GitHub Actions for CI: `.github/workflows/ci.yml`

---

### Phase 8 — Observability

| Variable | Service | Where to Get | Notes |
|----------|---------|-------------|-------|
| `LANGSMITH_API_KEY` | LangSmith tracing | https://smith.langchain.com | Set `LANGCHAIN_TRACING_V2=true` too |
| `LANGCHAIN_PROJECT` | LangSmith project name | Set to `nexuslearn-prod` | Tags all traces |

**Python packages:**
```
langsmith
pytest
pytest-asyncio
httpx            # for FastAPI test client
ruff             # linting
```

---

## 🐳 Docker Setup (Phase 8)

**docker-compose.yml services needed:**
- `backend` — FastAPI on port 8000
- `postgres` — Postgres 15+ with pgvector extension
- `redis` — Redis 7+

**Docker images:**
```yaml
postgres: pgvector/pgvector:pg16    # has pgvector pre-installed
redis:    redis:7-alpine
```

---

## 🚀 Deployment URLs

| Service | URL | Notes |
|---------|-----|-------|
| Railway (backend) | https://railway.app | Current backend host |
| Vercel (frontend) | https://vercel.com | Current frontend host |
| Railway Postgres | Add via Railway dashboard | |
| Railway Redis | Add via Railway dashboard | Check memory limits |
| Supabase (DB alt) | https://supabase.com | Free pgvector included |
| Neon (DB alt) | https://neon.tech | Free pgvector included |
| Upstash (Redis alt) | https://upstash.com | Serverless, free tier |

---

## 📄 .env.example Template

Create this file at repo root and commit it (no real values):

```env
# ── LLM Providers ──────────────────────────────────
GROQ_API_KEY=your_groq_key_here
MISTRAL_API_KEY=your_mistral_key_here
GEMINI_API_KEY=your_gemini_key_here          # optional
TAVILY_API_KEY=your_tavily_key_here          # optional

# ── Database ───────────────────────────────────────
DATABASE_URL=postgresql://user:pass@host:5432/nexuslearn

# ── Redis ──────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── Auth (if building own JWT) ─────────────────────
JWT_SECRET_KEY=generate_with_secrets_token_hex_32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ── Observability ──────────────────────────────────
LANGSMITH_API_KEY=your_langsmith_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=nexuslearn-prod

# ── App Config ─────────────────────────────────────
ENVIRONMENT=development                       # development | production
MAX_FILE_SIZE_MB=50
MAX_FILES_PER_USER=20
MAX_REQUESTS_PER_DAY=100
```

---

## 📋 Installation Commands by Phase

### Phase 1 — Eval
```bash
pip install ragas==<pinned_version> datasets pandas numpy
# check latest: pip index versions ragas
```

### Phase 2 — Postgres + pgvector
```bash
pip install psycopg2-binary pgvector alembic sqlalchemy asyncpg
# init alembic:
alembic init alembic
```

### Phase 3 — Auth
```bash
pip install PyJWT argon2-cffi python-multipart
```

### Phase 5 — Redis
```bash
pip install redis fastapi-limiter
# OR for rate limiting:
pip install slowapi
# FOR async job queue:
pip install arq
```

### Phase 7 — Security
```bash
pip install pip-audit ruff
# garak:
pip install garak
# promptfoo (Node):
npm install -g promptfoo
```

### Phase 8 — Observability + Testing
```bash
pip install langsmith pytest pytest-asyncio httpx
```

---

## ✅ Verify-Before-You-Rely List

Items to manually verify (from SKILL.md):

- [ ] Current latest `ragas` version and exact metric class signatures
- [ ] pgvector availability on your specific Railway plan
- [ ] Mistral embedding dimension — confirm it's `1024` for `mistral-embed` (affects `vector(N)` column)
- [ ] Railway Redis current pricing and memory limits
- [ ] Current license and status of Promptfoo and garak before citing in report
- [ ] Groq org-level rate limits docs — read before any key strategy decisions
