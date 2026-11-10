"""
NexusLearn AI — Application Settings
All configuration is driven by environment variables.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # ── App ──────────────────────────────────────────
    app_name: str = "NexusLearn AI"
    environment: str = "development"
    debug: bool = False

    # ── CORS ─────────────────────────────────────────
    frontend_url: str = "http://localhost:5173"

    # ── Database ─────────────────────────────────────
    # PostgreSQL + pgvector (production)
    # Leave empty to fall back to FAISS (local dev)
    database_url: str = ""

    # ── Redis ────────────────────────────────────────
    # Leave empty to disable caching/rate-limiting
    redis_url: str = ""

    # ── JWT ──────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production-use-secrets-token-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── LLM Providers ────────────────────────────────
    groq_api_key: str = ""
    mistral_api_key: str = ""
    gemini_api_key: str = ""
    tavily_api_key: str = ""

    # ── LangSmith ────────────────────────────────────
    langsmith_api_key: str = ""
    langchain_tracing_v2: bool = False
    langchain_project: str = "nexuslearn"

    # ── File Limits ──────────────────────────────────
    max_file_size_mb: int = 50
    max_files_per_user: int = 20
    max_requests_per_day: int = 200

    # ── Circuit Breaker ──────────────────────────────
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_timeout: int = 60  # seconds

    # ── Retrieval ────────────────────────────────────
    default_chunk_size: int = 1000
    default_chunk_overlap: int = 200
    default_top_k: int = 5
    rerank_top_n: int = 20  # fetch this many before reranking


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
