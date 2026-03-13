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

# Ensure `import config` and other project-local absolute imports work.
_PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from enterprise_api.config import load_dotenv_if_available

# Load .env (optional) BEFORE initializing DB engine.
load_dotenv_if_available()

from enterprise_api.db.models import Message, Run
from enterprise_api.db.session import get_session, init_db
from enterprise_api.parsing import extract_citations, summarize_openbb_tool_calls
from enterprise_api.audit_sync import copy_openbb_audit_to_enterprise, list_tool_calls_for_run

from openbb.storage import set_current_run_id

# Lazy imports for heavy RAG components


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(None, description="Optional conversation id")
    message: str = Field(..., min_length=1, description="User message")


class ChatResponse(BaseModel):
    run_id: str
    answer: str
    citations: List[str]
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
    citations: List[str]
    openbb_used: Dict[str, Any]
    tool_calls: List[Dict[str, Any]]


init_db()

app = FastAPI(title="Agentic RAG Enterprise API", version="0.1.0")


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


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

    from core.chat_interface import ChatInterface

    rag = _get_rag_system_for_conversation(conversation_id)
    chat_interface = ChatInterface(rag)

    answer = chat_interface.chat(req.message, history=[])
    citations = extract_citations(answer)

    db = get_session()
    try:
        run_row = Run(
            id=run_id,
            conversation_id=conversation_id,
            status="completed",
            user_message=req.message,
            answer=answer,
            citations_json=json.dumps(citations, ensure_ascii=False),
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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        # Clear run_id context
        set_current_run_id(None)

    return ChatResponse(run_id=run_id, answer=answer, citations=citations, openbb_used=openbb_used)


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

        citations: List[str] = []
        if run.citations_json:
            try:
                citations = json.loads(run.citations_json)
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
            citations=citations,
            openbb_used=openbb_used,
            tool_calls=tool_calls,
        )
    finally:
        db.close()
