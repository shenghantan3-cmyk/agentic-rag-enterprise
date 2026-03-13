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

    Note: create_all does not add new columns to existing tables. For local
    SQLite usage we apply a tiny best-effort migration for additive columns.
    """

    global _SessionLocal
    engine = get_engine()
    if create_schema:
        Base.metadata.create_all(bind=engine)

        # Best-effort additive migration for SQLite.
        try:
            if str(engine.url).startswith("sqlite"):
                with engine.connect() as conn:
                    cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(runs)").fetchall()]
                    if "citations_payload_json" not in cols:
                        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN citations_payload_json TEXT")

                    # Create jobs table if missing (best-effort).
                    tbls = [r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    if "jobs" not in tbls:
                        conn.exec_driver_sql(
                            """
                            CREATE TABLE jobs (
                              id VARCHAR(64) PRIMARY KEY,
                              kind VARCHAR(64) NOT NULL,
                              status VARCHAR(32) NOT NULL,
                              created_at DATETIME NOT NULL,
                              started_at DATETIME,
                              finished_at DATETIME,
                              progress INTEGER NOT NULL DEFAULT 0,
                              message TEXT,
                              doc_id VARCHAR(128),
                              payload_json TEXT,
                              result_json TEXT,
                              error TEXT,
                              metrics_json TEXT
                            )
                            """
                        )
                        conn.exec_driver_sql("CREATE INDEX ix_jobs_kind ON jobs (kind)")
                        conn.exec_driver_sql("CREATE INDEX ix_jobs_status ON jobs (status)")
        except Exception:
            # Never break startup for best-effort migrations.
            pass

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    """Get a new DB session (initializes DB on first use)."""
    global _SessionLocal
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()
