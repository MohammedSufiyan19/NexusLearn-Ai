"""
NexusLearn AI — Database Session
Creates SQLAlchemy engine for PostgreSQL (production) or SQLite (local dev).
"""
# pyrefly: ignore[missing-import]
from app.core.config import settings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def _make_engine():
    db_url = settings.database_url or "sqlite:///./nexuslearn_dev.db"

    if db_url.startswith("postgresql"):
        # Production: PostgreSQL + pgvector
        engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # detect stale connections
            echo=settings.debug,
        )
        # Enable pgvector extension on first connect
        @event.listens_for(engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                dbapi_connection.commit()
                cursor.close()
            except Exception:
                pass  # extension may already exist

    else:
        # SQLite (dev or test)
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in db_url:
            from sqlalchemy.pool import StaticPool
            kwargs["poolclass"] = StaticPool
        engine = create_engine(db_url, echo=settings.debug, **kwargs)

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables (run on startup)."""
    # pyrefly: ignore[missing-import]
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
