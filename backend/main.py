"""
NexusLearn AI — Main Application (v2.0)
Refactored with:
  - JWT authentication & per-user isolation
  - PostgreSQL + pgvector OR FAISS (local dev)
  - Redis caching & rate limiting (optional)
  - Circuit breaker for LLM providers
  - Prompt injection defences
  - Audit logging
  - Strict CORS (frontend origin only)
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

# Ensure backend directory is in sys.path so 'app' is always resolvable
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env from backend/ directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
# Also try root-level .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.core.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── LangSmith tracing (optional) ─────────────────────────────────────────────
if settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    logger.info("LangSmith tracing enabled (project: %s)", settings.langchain_project)


# ── Lifespan Handler ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NexusLearn AI v2.0 (env=%s)", settings.environment)

    # Init database
    try:
        from app.db.session import init_db
        init_db()
        logger.info("Database initialized (%s)", "postgres" if settings.database_url.startswith("postgresql") else "sqlite")
    except Exception as exc:
        logger.warning("DB init skipped: %s — running in FAISS mode", exc)

    # Test Redis
    if settings.redis_url:
        from app.cache.redis_client import get_redis_client
        r = get_redis_client()
        if r:
            logger.info("Redis connected")
        else:
            logger.warning("Redis configured but unavailable — running without cache")

    yield


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="NexusLearn AI",
    description="Intelligent Academic RAG Assistant — v2.0 with auth, isolation, and eval",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────
# IMPORTANT: Never use allow_origins=["*"] in production — locks down to frontend URL
_origins = [settings.frontend_url]
if settings.environment == "development":
    _origins += ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Security Headers Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.environment != "development":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)


# ── Legacy compatibility routes (keeps old frontend working without auth) ─────
# These wrap the new authenticated endpoints with a bypass for demo/FAISS mode


from fastapi import BackgroundTasks, File, UploadFile
from pydantic import BaseModel


class _LegacyChatReq(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/upload")
async def legacy_upload(background_tasks: BackgroundTasks, request: Request, file: UploadFile = File(...)):
    """Legacy upload route (no auth) — works only in FAISS/demo mode."""
    if settings.database_url:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": "Auth required — use POST /documents with Bearer token"}
        )
    # In demo mode, create a fake current_user
    from app.core.deps import CurrentUser
    fake_user = CurrentUser(user_id="demo", email="demo@nexuslearn.ai", role="student")
    from app.api.documents import upload_document
    return await upload_document(background_tasks, request, file, current_user=fake_user, db=None)


@app.post("/chat")
def legacy_chat(req: _LegacyChatReq, request: Request):
    """Legacy chat route (no auth) — works in FAISS/demo mode."""
    if settings.database_url:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": "Auth required — use POST /chat with Bearer token"}
        )
    from app.api.chat import ChatRequest, chat
    from app.core.deps import CurrentUser
    fake_user = CurrentUser(user_id="demo", email="demo@nexuslearn.ai", role="student")
    chat_req = ChatRequest(message=req.message, history=req.history)
    return chat(chat_req, request, current_user=fake_user, db=None)


@app.get("/sources")
def legacy_sources(request: Request):
    """Legacy sources route (no auth) — returns FAISS sources."""
    from app.api.documents import list_sources
    from app.core.deps import CurrentUser
    fake_user = CurrentUser(user_id="demo", email="demo@nexuslearn.ai", role="student")
    return list_sources(current_user=fake_user, db=None)


@app.delete("/clear")
def legacy_clear():
    """Legacy clear — only works in FAISS mode."""
    if settings.database_url:
        return JSONResponse(
            status_code=410,
            content={"detail": "Use DELETE /me/data with auth"}
        )
    import shutil
    faiss_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "vectorstore", "faiss_index")
    )
    if os.path.exists(faiss_path):
        shutil.rmtree(faiss_path)
    return {"message": "Vector store cleared"}
