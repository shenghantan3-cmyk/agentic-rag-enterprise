from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rq import get_current_job

# Ensure `import core` and `import enterprise_api` work (see enterprise_api/app.py).
_PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from enterprise_api.db.models import Job
from enterprise_api.db.session import get_session


def _set_progress(*, job_id: str, progress: int, message: str | None = None) -> None:
    db = get_session()
    try:
        row = db.query(Job).filter(Job.id == job_id).one_or_none()
        if not row:
            return
        row.progress = int(progress)
        if message is not None:
            row.message = message
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ingest_document(*, doc_id: str, file_path: str) -> dict[str, Any]:
    """Ingest a single uploaded document into the vector store.

    Returns a dict that will be stored as Job.result_json.
    """

    rq_job = get_current_job()
    job_id = str(rq_job.id) if rq_job else ""

    start = time.perf_counter()

    db = get_session()
    try:
        row = db.query(Job).filter(Job.id == job_id).one_or_none()
        if row:
            row.status = "running"
            row.started_at = datetime.utcnow()
            row.progress = 0
            row.message = "starting"
            row.doc_id = doc_id
            db.commit()
    except Exception:
        db.rollback()
        # Continue even if DB update fails (best effort)
    finally:
        db.close()

    def progress_cb(frac: float, msg: str) -> None:
        # DocumentManager gives 0..1. Clamp and map to 5..95.
        try:
            pct = int(max(0.0, min(1.0, float(frac))) * 90) + 5
        except Exception:
            pct = 5
        _set_progress(job_id=job_id, progress=pct, message=msg)

    try:
        from core.rag_system import RAGSystem
        from core.document_manager import DocumentManager

        rag = RAGSystem()
        rag.initialize()
        dm = DocumentManager(rag)

        _set_progress(job_id=job_id, progress=5, message="ingesting")
        added, skipped = dm.add_documents([file_path], progress_callback=progress_cb)

        elapsed = time.perf_counter() - start
        result = {
            "doc_id": doc_id,
            "added": int(added),
            "skipped": int(skipped),
        }
        metrics = {
            "duration_ms": int(elapsed * 1000),
        }

        db = get_session()
        try:
            row = db.query(Job).filter(Job.id == job_id).one_or_none()
            if row:
                row.status = "completed"
                row.finished_at = datetime.utcnow()
                row.progress = 100
                row.message = "completed"
                row.result_json = json.dumps(result, ensure_ascii=False)
                row.metrics_json = json.dumps(metrics, ensure_ascii=False)
                row.error = None
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # cleanup best effort
        try:
            p = Path(file_path)
            if p.exists() and p.is_file() and p.parent.name == "agentic_rag_uploads":
                p.unlink(missing_ok=True)
        except Exception:
            pass

        return {"result": result, "metrics": metrics}

    except Exception as e:
        db = get_session()
        try:
            row = db.query(Job).filter(Job.id == job_id).one_or_none()
            if row:
                row.status = "failed"
                row.finished_at = datetime.utcnow()
                row.message = "failed"
                row.error = str(e)
                row.progress = max(int(row.progress or 0), 0)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        raise


def noop(*, seconds: float = 0.1) -> dict[str, Any]:
    """A small dummy job used for smoke testing."""

    rq_job = get_current_job()
    job_id = str(rq_job.id) if rq_job else ""

    db = get_session()
    try:
        row = db.query(Job).filter(Job.id == job_id).one_or_none()
        if row:
            row.status = "running"
            row.started_at = datetime.utcnow()
            row.progress = 0
            row.message = "running"
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    time.sleep(max(0.0, float(seconds)))

    db = get_session()
    try:
        row = db.query(Job).filter(Job.id == job_id).one_or_none()
        if row:
            row.status = "completed"
            row.finished_at = datetime.utcnow()
            row.progress = 100
            row.message = "completed"
            row.result_json = json.dumps({"ok": True, "seconds": seconds}, ensure_ascii=False)
            row.metrics_json = json.dumps({"duration_ms": int(seconds * 1000)}, ensure_ascii=False)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"ok": True, "seconds": seconds}
