"""
connection.py
--------------
Central database connectivity layer for RESOLVIX-AI.

Responsibilities:
    - Build the SQLAlchemy engine from environment variables (.env)
    - Provide a scoped Session factory
    - Expose a FastAPI dependency (`get_db`) for request-scoped sessions
    - Provide `init_db()` for first-run table creation (dev only — use
      Alembic migrations in migrations/ for staging/production)
    - Provide an async engine/session for services that need async I/O
      (e.g. streaming AI agent responses, websocket chat)

Usage in other modules:
    from backend.database.connection import get_db, Base, engine

    @router.get("/complaints")
    def list_complaints(db: Session = Depends(get_db)):
        return db.query(Complaint).all()
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    ASYNC_SUPPORTED = True
except ImportError:
    ASYNC_SUPPORTED = False

logger = logging.getLogger("resolvix.database")

# ---------------------------------------------------------------------------
# Configuration (pulled from .env — see docker-compose.yml for defaults)
# ---------------------------------------------------------------------------
DB_USER = os.getenv("POSTGRES_USER", "resolvix_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "resolvix_pass")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "resolvix_ai")

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./resolvix.db"
)



# Async URL (asyncpg driver) — used by AI agents / websocket services
ASYNC_DATABASE_URL = os.getenv(
    "ASYNC_DATABASE_URL",
    SQLALCHEMY_DATABASE_URL.replace("postgresql+psycopg2", "postgresql+asyncpg"),
)

ECHO_SQL = os.getenv("SQL_ECHO", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Synchronous engine (used by FastAPI request handlers, admin scripts)
# ---------------------------------------------------------------------------
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=ECHO_SQL,
        future=True,
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=QueuePool,
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=ECHO_SQL,
        future=True,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)

Base = declarative_base()

# ---------------------------------------------------------------------------
# Async engine (optional — only wired up if asyncpg is installed)
# ---------------------------------------------------------------------------
# Create async engine only for PostgreSQL
if ASYNC_SUPPORTED and SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=ECHO_SQL,
        pool_pre_ping=True,
        future=True,
    )

    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def get_async_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# ---------------------------------------------------------------------------
# FastAPI dependency — synchronous
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """
    Request-scoped DB session. Guarantees rollback on error and
    always closes the connection back to the pool.

    Example:
        @router.post("/complaints")
        def create_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context-manager version for use OUTSIDE FastAPI request handlers —
    background jobs, AI agents, CLI scripts, Celery tasks.

    Example:
        with db_session() as db:
            complaint = db.query(Complaint).get(complaint_id)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Connection health check (used by monitoring/health_check.py)
# ---------------------------------------------------------------------------
def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Dev-only bootstrap. Production/staging MUST use Alembic
# (backend/database/migrations/) instead of this.
# ---------------------------------------------------------------------------
def init_db():
    import database.models # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created (dev bootstrap).")


@event.listens_for(engine, "connect")
def _set_search_path(dbapi_connection, connection_record):
    # PostgreSQL only
    if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()
