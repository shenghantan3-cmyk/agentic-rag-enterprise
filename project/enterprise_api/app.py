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

from fastapi import FastAPI, File, HTTPException, UploadFile
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

from enterprise_api.db.models import Message, Run
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


class UploadResponse(BaseModel):
    doc_id: str


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


@app.post("/v1/documents/upload", response_model=UploadResponse)
def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md"}:
        raise HTTPException(status_code=400, detail="Only .pdf and .md are supported")

    # Save upload to a temp file for DocumentManager.
    tmp_dir = Path(tempfile.gettempdir()) / "agentic_rag_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    doc_id = f"{Path(filename).stem}-{uuid.uuid4().hex[:8]}"
    tmp_path = tmp_dir / f"{doc_id}{suffix}"

    try:
        data = file.file.read()
        tmp_path.write_bytes(data)

        from core.rag_system import RAGSystem
        from core.document_manager import DocumentManager

        rag = RAGSystem()
        rag.initialize()
        dm = DocumentManager(rag)
        added, skipped = dm.add_documents([str(tmp_path)])

        if added <= 0 and skipped > 0:
            # likely duplicate
            pass

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return UploadResponse(doc_id=doc_id)


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
