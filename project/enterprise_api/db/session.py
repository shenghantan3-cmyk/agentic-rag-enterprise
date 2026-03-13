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
        _ENGINE = create_engine(settings.database_url, future=True)
    return _ENGINE


def init_db() -> None:
    """Initialize database and session factory."""
    global _SessionLocal
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    """Get a new DB session (initializes DB on first use)."""
    global _SessionLocal
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()
