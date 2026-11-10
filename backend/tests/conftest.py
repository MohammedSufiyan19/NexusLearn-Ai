"""
Pytest configuration and fixtures for NexusLearn AI backend.
Uses a file-based SQLite database with automatic table creation and clean teardown.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path(__file__).parent / "test_suite.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-tests-minimum-32-chars-long"
os.environ["ENVIRONMENT"] = "test"
os.environ["GROQ_API_KEY"] = "mock-groq-key"
os.environ["MISTRAL_API_KEY"] = "mock-mistral-key"

from app.core.config import get_settings

# Clear lru_cache so settings reloads with TEST environment variables
get_settings.cache_clear()
settings = get_settings()

from app.db.models import Base
from app.db.session import SessionLocal, engine
from main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all database tables for the test session and clean up on exit."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass


@pytest.fixture
def db():
    """Provide a clean session per test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
