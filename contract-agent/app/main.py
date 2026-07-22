"""
Contract Agent web API (MVP).

FastAPI app that exposes the analysis pipeline over HTTP and serves a
small single-page UI from app/static.

Because a full contract analysis on a local 7B model can take minutes,
uploads are handled as background jobs:

  POST /api/analyze        -> saves the file, starts a job, returns job_id
  GET  /api/jobs/{job_id}  -> live status + per-clause progress + result

Jobs are kept in an in-memory dict, which is fine for a single-process
MVP. Analysis runs on a dedicated worker thread; jobs are processed one
at a time because the local model can't serve concurrent requests.
"""

import queue
import sys
import tempfile
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

# The src modules import each other with bare names (e.g. "from chunking
# import Chunk"), so src/ itself must be on sys.path.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline import PipelineError, analyze_contract

STATIC_DIR = Path(__file__).resolve().parent / "static"
ALLOWED_SUFFIXES = {".pdf", ".txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

app = FastAPI(title="Contract Agent", version="0.1.0")

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_work_queue: "queue.Queue[str]" = queue.Queue()


def _serialize_report(report) -> dict:
    return {
        "verdicts": [asdict(v) for v in report.verdicts],
        "failed_chunk_indices": report.failed_chunk_indices,
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "total_clauses": len(report.verdicts) + len(report.failed_chunk_indices),
    }


def _worker_loop() -> None:
    """Process jobs one at a time on a single thread."""
    while True:
        job_id = _work_queue.get()
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                continue
            job["status"] = "running"
            file_path = job["file_path"]

        def on_progress(done: int, total: int) -> None:
            with _jobs_lock:
                _jobs[job_id]["progress"] = {"done": done, "total": total}

        try:
            report = analyze_contract(file_path, progress_callback=on_progress)
            result = _serialize_report(report)
            with _jobs_lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["result"] = result
        except PipelineError as e:
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = str(e)
        except Exception as e:  # unexpected -- surface it rather than hang the job
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = f"Unexpected error: {e}"
        finally:
            Path(file_path).unlink(missing_ok=True)


_worker = threading.Thread(target=_worker_loop, daemon=True, name="analysis-worker")
_worker.start()


@app.post("/api/analyze")
async def start_analysis(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"'{suffix or '(no extension)'}' files aren't supported. "
            "Please upload a .pdf or .txt file.",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 20 MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "filename": file.filename,
            "file_path": tmp_path,
            "progress": {"done": 0, "total": 0},
        }
    _work_queue.put(job_id)

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id.")
        return {
            "job_id": job_id,
            "status": job["status"],
            "filename": job["filename"],
            "progress": job["progress"],
            "result": job.get("result"),
            "error": job.get("error"),
        }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
