from __future__ import annotations

"""FastAPI enterprise API.

Note: existing code in this repo uses `import config` (module in project/).
To keep backwards compatibility, we insert the project directory into sys.path.
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from pydantic import BaseModel, Field


import time
import logging

# Ensure `import config` and other project-local absolute imports work.
_PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from enterprise_api.auth import ApiKeyAuthMiddleware
from enterprise_api.metrics import (
    MetricsMiddleware,
    metrics_enabled,
    metrics_response,
    observe_chat_duration,
    observe_tool_calls,
)
from enterprise_api.observability import (
    RequestContextMiddleware,
    log_fields,
    set_run_id,
    setup_json_logging,
)

from enterprise_api.config import load_dotenv_if_available
from common.citations import citations_to_files
from enterprise_api.schemas import Citation

# Load .env (optional) BEFORE initializing DB engine.
load_dotenv_if_available()

from enterprise_api.db.models import Job, Message, Run
from enterprise_api.db.session import get_session, init_db
from enterprise_api.parsing import summarize_openbb_tool_calls
from enterprise_api.audit_sync import copy_openbb_audit_to_enterprise, list_tool_calls_for_run

from openbb.storage import set_current_run_id

# Lazy imports for heavy RAG components


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(None, description="Optional conversation id")
    message: str = Field(..., min_length=1, description="User message")


class ChatResponse(BaseModel):
    run_id: str
    answer: str

    # New: structured citations (end-to-end)
    citations: List[Citation] = Field(default_factory=list)
    # Backward-compatible filenames list.
    citation_files: List[str] = Field(default_factory=list)

    openbb_used: Dict[str, Any]


class EnqueueResponse(BaseModel):
    job_id: str
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    progress: int = 0
    message: Optional[str] = None
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class RunResponse(BaseModel):
    run_id: str
    conversation_id: Optional[str]
    created_at: str
    status: str
    user_message: str
    answer: str

    citations: List[Citation] = Field(default_factory=list)
    citation_files: List[str] = Field(default_factory=list)

    openbb_used: Dict[str, Any]
    tool_calls: List[Dict[str, Any]]


logger = logging.getLogger("enterprise_api")
setup_json_logging()

app = FastAPI(title="Agentic RAG Enterprise API", version="0.1.0")

# Middleware order: auth -> request context -> metrics
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RequestContextMiddleware)
if metrics_enabled():
    app.add_middleware(MetricsMiddleware)


@app.on_event("startup")
def _startup() -> None:
    # In local dev (sqlite), create tables automatically.
    # In compose/prod (postgres), Alembic should have created tables.
    try:
        db_url = os.getenv("DATABASE_URL", "")
        create_schema = (not db_url) or db_url.startswith("sqlite")
        init_db(create_schema=create_schema)
    except Exception as e:
        logger.error("db init failed", extra=log_fields(error=str(e)))
        raise


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Any:
    return metrics_response()


def _get_rag_system_for_conversation(conversation_id: Optional[str]):
    from core.rag_system import RAGSystem

    rag = RAGSystem()
    rag.initialize()
    if conversation_id:
        rag.thread_id = str(conversation_id)
    return rag


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    conversation_id = req.conversation_id
    run_id = str(uuid.uuid4())

    # Attach run_id to OpenBB tool audit logs via ContextVar.
    set_current_run_id(run_id)
    # Attach run_id to app logs.
    set_run_id(run_id)

    start = time.perf_counter()

    copied: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    openbb_used: Dict[str, Any] = {"count": 0, "endpoints": [], "cache_hits": 0, "avg_latency_ms": None}
    ok = False
    err: Optional[str] = None

    try:
        from core.chat_interface import ChatInterface

        rag = _get_rag_system_for_conversation(conversation_id)
        chat_interface = ChatInterface(rag)

        answer, citations = chat_interface.chat_with_citations(req.message, history=[])

        db = get_session()
        try:
            run_row = Run(
                id=run_id,
                conversation_id=conversation_id,
                status="completed",
                user_message=req.message,
                answer=answer,
                citations_json=json.dumps(citations_to_files(citations), ensure_ascii=False),
                citations_payload_json=json.dumps(citations, ensure_ascii=False),
                openbb_summary_json=None,
                error=None,
            )
            db.add(run_row)
            db.add(Message(run_id=run_id, conversation_id=conversation_id, role="user", content=req.message))
            db.add(Message(run_id=run_id, conversation_id=conversation_id, role="assistant", content=answer))

            # Copy OpenBB audit rows into enterprise DB and compute summary.
            copied = copy_openbb_audit_to_enterprise(run_id=run_id, db=db)
            openbb_used = summarize_openbb_tool_calls(copied)
            run_row.openbb_summary_json = json.dumps(openbb_used, ensure_ascii=False)

            db.commit()
            ok = True
        except Exception as e:
            db.rollback()
            err = str(e)
            logger.exception("chat failed", extra=log_fields(error=err))
            raise HTTPException(status_code=500, detail=err)
        finally:
            db.close()

        return ChatResponse(
            run_id=run_id,
            answer=answer,
            citations=[Citation(**c) for c in (citations or [])],
            citation_files=citations_to_files(citations),
            openbb_used=openbb_used,
        )

    finally:
        # metrics and logging (run even on failure)
        elapsed = time.perf_counter() - start
        observe_chat_duration(elapsed)
        observe_tool_calls([{"provider": "openbb", **tc} for tc in (copied or [])])

        logger.info(
            "chat finished",
            extra=log_fields(
                conversation_id=conversation_id,
                status="completed" if ok else "error",
                error=err,
                elapsed_ms=int(elapsed * 1000),
                citations_count=len(citations),
                tool_calls=len(copied or []),
            ),
        )

        # Clear run_id contexts
        set_current_run_id(None)
        set_run_id(None)


@app.post("/v1/documents/upload", response_model=EnqueueResponse)
def upload_document(request: Request, file: UploadFile = File(...)) -> EnqueueResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md"}:
        raise HTTPException(status_code=400, detail="Only .pdf and .md are supported")

    # Save upload to a local path that is also visible to the worker.
    # In docker-compose, both enterprise-api and worker should mount the same directory.
    upload_root = Path(os.getenv("ENTERPRISE_UPLOAD_DIR") or (Path(tempfile.gettempdir()) / "agentic_rag_uploads"))
    upload_root.mkdir(parents=True, exist_ok=True)
    doc_id = f"{Path(filename).stem}-{uuid.uuid4().hex[:8]}"
    tmp_path = upload_root / f"{doc_id}{suffix}"

    from enterprise_api.queue import get_queue

    # We set an explicit job id so DB and queue share the same identifier.
    job_id = uuid.uuid4().hex

    db = get_session()
    try:
        db.add(
            Job(
                id=job_id,
                kind="document_ingest",
                status="queued",
                progress=0,
                message="queued",
                doc_id=doc_id,
                payload_json=json.dumps(
                    {
                        "filename": filename,
                        "content_type": file.content_type,
                        "file_path": str(tmp_path),
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    try:
        data = file.file.read()
        tmp_path.write_bytes(data)

        q = get_queue()
        q.enqueue(
            "enterprise_api.tasks.ingest_document",
            job_id=job_id,
            kwargs={"doc_id": doc_id, "file_path": str(tmp_path)},
        )
    except Exception as e:
        # Mark failed if enqueue fails.
        db = get_session()
        try:
            row = db.query(Job).filter(Job.id == job_id).one_or_none()
            if row:
                row.status = "failed"
                row.error = str(e)
                row.message = "enqueue failed"
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        raise HTTPException(status_code=500, detail=str(e))

    status_url = str(request.base_url).rstrip("/") + f"/v1/jobs/{job_id}"
    return EnqueueResponse(job_id=job_id, status_url=status_url)


@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    db = get_session()
    try:
        row = db.query(Job).filter(Job.id == job_id).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="job not found")

        result: Optional[Dict[str, Any]] = None
        if row.result_json:
            try:
                result = json.loads(row.result_json)
            except Exception:
                result = None

        metrics: Optional[Dict[str, Any]] = None
        if row.metrics_json:
            try:
                metrics = json.loads(row.metrics_json)
            except Exception:
                metrics = None

        created_at = row.created_at.isoformat() + "Z" if row.created_at else ""
        started_at = row.started_at.isoformat() + "Z" if row.started_at else None
        finished_at = row.finished_at.isoformat() + "Z" if row.finished_at else None

        return JobStatusResponse(
            job_id=row.id,
            kind=row.kind,
            status=row.status,
            progress=int(row.progress or 0),
            message=row.message,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            result=result,
            error=row.error,
            metrics=metrics,
        )
    finally:
        db.close()


@app.post("/v1/jobs/noop", response_model=EnqueueResponse)
def enqueue_noop(request: Request, seconds: float = 0.1) -> EnqueueResponse:
    from enterprise_api.queue import get_queue

    job_id = uuid.uuid4().hex

    db = get_session()
    try:
        db.add(
            Job(
                id=job_id,
                kind="noop",
                status="queued",
                progress=0,
                message="queued",
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    try:
        q = get_queue()
        q.enqueue(
            "enterprise_api.tasks.noop",
            job_id=job_id,
            kwargs={"seconds": float(seconds)},
        )
    except Exception as e:
        db = get_session()
        try:
            row = db.query(Job).filter(Job.id == job_id).one_or_none()
            if row:
                row.status = "failed"
                row.error = str(e)
                row.message = "enqueue failed"
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        raise HTTPException(status_code=500, detail=str(e))

    status_url = str(request.base_url).rstrip("/") + f"/v1/jobs/{job_id}"
    return EnqueueResponse(job_id=job_id, status_url=status_url)


@app.get("/v1/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> RunResponse:
    db = get_session()
    try:
        run = db.query(Run).filter(Run.id == run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="run not found")

        citation_files: List[str] = []
        if run.citations_json:
            try:
                citation_files = json.loads(run.citations_json)
            except Exception:
                citation_files = []

        citations: List[Dict[str, Any]] = []
        if getattr(run, "citations_payload_json", None):
            try:
                citations = json.loads(run.citations_payload_json)  # type: ignore[attr-defined]
            except Exception:
                citations = []

        openbb_used: Dict[str, Any] = {"count": 0, "endpoints": [], "cache_hits": 0, "avg_latency_ms": None}
        if run.openbb_summary_json:
            try:
                openbb_used = json.loads(run.openbb_summary_json)
            except Exception:
                pass

        tool_calls = list_tool_calls_for_run(run_id=run_id, db=db)

        created_at = run.created_at.isoformat() + "Z" if run.created_at else ""
        return RunResponse(
            run_id=run.id,
            conversation_id=run.conversation_id,
            created_at=created_at,
            status=run.status,
            user_message=run.user_message,
            answer=run.answer,
            citations=[Citation(**c) for c in (citations or [])],
            citation_files=citation_files,
            openbb_used=openbb_used,
            tool_calls=tool_calls,
        )
    finally:
        db.close()
