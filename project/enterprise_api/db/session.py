from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from .models import Base

_ENGINE: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        settings = get_settings()
        # pool_pre_ping helps with stale connections in multi-worker deployments.
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            # sqlite needs this for multi-threaded web servers
            connect_args = {"check_same_thread": False}
        _ENGINE = create_engine(
            settings.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _ENGINE


def init_db(*, create_schema: bool = True) -> None:
    """Initialize database and session factory.

    For production Postgres, prefer Alembic migrations instead of create_all.
    We keep create_all as a local-dev fallback (and for SQLite).
    """

    global _SessionLocal
    engine = get_engine()
    if create_schema:
        Base.metadata.create_all(bind=engine)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    """Get a new DB session (initializes DB on first use)."""
    global _SessionLocal
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()
