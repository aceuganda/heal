"""Admin API for the approved-source library.

Everything the `admin/sources` screen needs. Auth uses the same
`current_admin_user` dependency as the rest of the admin surface, which is a
no-op when AUTH_TYPE=disabled -- so a local stack is open without a special
bypass that would later have to be found and removed.

Two properties are deliberate and should survive hardening:

  * Uploading and approving are separate calls. Retrieval only ever returns
    approved chunks, so a document lands inert and a person has to endorse it.
  * `/search` returns raw scores, including hits below the floor. Tuning
    MIN_RETRIEVAL_SCORE is impossible without seeing what was just missed.
"""
import threading
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from heal import config
from heal.knowledge import extract as extraction
from heal.knowledge import jobs
from heal.knowledge.ingest import reference_ingest
from heal.knowledge.ingest import set_approval
from heal.knowledge.ingest import supersede
from heal.knowledge.store import collection_stats
from heal.knowledge.store import delete_source
from heal.knowledge.store import ensure_collection
from heal.knowledge.store import list_sources
from heal.knowledge.store import QdrantKnowledgeStore
from heal.logger import get_logger
from heal_app.auth.users import current_admin_user
from heal_app.db.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/manage/knowledge")

# Refused before the file is read into memory.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Phase names the ingest reports, in words an admin can act on.
_PHASE_LABELS = {
    "embedding": "Embedding and indexing",
    "approving": "Approving",
}


class SourceSummary(BaseModel):
    source_id: str
    title: str
    version: str
    publisher: str = ""
    published: str = ""
    approved: bool
    is_current: bool
    chunks: int


class IngestResponse(BaseModel):
    """What the upload returns now: a handle, not a result.

    Indexing a real guideline is minutes of CPU. Returning only when it is done
    meant the browser held the connection until the proxy killed it and
    reported failure for work that was still succeeding. The caller gets a job
    id immediately and polls `/jobs/{job_id}` for progress.
    """

    job_id: str
    status: str
    title: str
    kind: str = "text"
    pages: int = 0


class JobStatus(BaseModel):
    job_id: str
    title: str
    status: str
    phase: str
    chunks_done: int
    chunks_total: int
    percent: int
    source_id: str = ""
    error: str | None = None
    started: str = ""
    finished: str | None = None


class SearchHit(BaseModel):
    title: str
    version: str
    text: str
    score: float
    dense_score: float
    sparse_score: float
    above_floor: bool


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    min_retrieval_score: float
    best_score: float = 0.0
    below_floor: bool = False
    unavailable: bool = False
    error: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool = True


class SupersedeRequest(BaseModel):
    keep_version: str


def _enabled() -> None:
    """Every route needs the store; say plainly when it is switched off.

    `make up` starts the vector store and leaves this on, so reaching here
    means the deployment set KNOWLEDGE_ENABLED=false deliberately.
    """
    if not config.KNOWLEDGE_ENABLED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Knowledge retrieval is switched off for this deployment "
                "(KNOWLEDGE_ENABLED=false), so sources cannot be managed."
            ),
        )


@router.get("/status")
def knowledge_status(_: User | None = Depends(current_admin_user)) -> dict[str, Any]:
    """Collection counts and the live tuning constants."""
    if not config.KNOWLEDGE_ENABLED:
        return {"enabled": False}
    try:
        return {"enabled": True, **collection_stats()}
    except Exception as exc:  # noqa: BLE001 -- surfaced as a banner, not a 500
        logger.error("Knowledge status unavailable: %s", exc)
        return {"enabled": True, "unavailable": True, "error": str(exc)}


@router.post("/init")
def init_collection(_: User | None = Depends(current_admin_user)) -> dict[str, str]:
    """Create the collection if absent. Idempotent and never destructive."""
    _enabled()
    ensure_collection()
    return {"collection": config.QDRANT_COLLECTION, "status": "ready"}


@router.get("/sources")
def get_sources(
    _: User | None = Depends(current_admin_user),
) -> list[SourceSummary]:
    _enabled()
    return [SourceSummary(**s) for s in list_sources()]


@router.post("/sources")
async def upload_source(
    file: UploadFile = File(...),
    title: str = Form(...),
    version: str = Form("1"),
    publisher: str = Form(""),
    published: str = Form(""),
    approve: bool = Form(False),
    user: User | None = Depends(current_admin_user),
) -> IngestResponse:
    """Extract the file, then index it in the background.

    Unapproved unless `approve` is set: retrieval filters on approval, so a
    document uploaded here cannot be cited until someone endorses it.

    The split is deliberate. Extraction runs here, in a worker thread, so a
    file that cannot be read is refused immediately with a reason. Embedding
    does not: a 1242-chunk guideline is minutes of CPU, and holding the request
    open for it meant nginx cut the connection at its timeout and reported
    failure for work that was still running. That returns a job id instead, and
    the caller polls `/jobs/{job_id}`.

    Either way the work never runs on the event loop -- doing so froze the
    whole API, `/health` included, until indexing finished.
    """
    _enabled()

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    try:
        extracted = await run_in_threadpool(
            extraction.extract, data, file.filename or "upload"
        )
    except extraction.ExtractionError as exc:
        # 422, not 500: the file is the problem and the message says how.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The actor is recorded on the run. Ingest refuses to be anonymous, and
    # with auth disabled there is no user, so the fallback is explicit rather
    # than silently blank.
    actor = getattr(user, "email", None) or "local-admin"

    job = jobs.registry.create(title=title)

    def _progress(phase: str, done: int, total: int) -> None:
        jobs.registry.update(
            job.job_id,
            phase=_PHASE_LABELS.get(phase, phase),
            chunks_done=done,
            chunks_total=total,
        )

    def _run() -> None:
        jobs.registry.update(job.job_id, status="running", phase="Reading document")
        try:
            result = reference_ingest(
                text=extracted.text,
                title=title,
                actor=actor,
                version=version,
                publisher=publisher,
                published=published,
                approved=approve,
                progress=_progress,
            )
        except Exception as exc:  # noqa: BLE001 -- the job carries the failure
            logger.error("Ingest thread died for job %s: %s", job.job_id, exc)
            jobs.registry.update(
                job.job_id, status=jobs.FAILED, phase="Failed", error=str(exc)
            )
            return

        if result.status == "failed":
            jobs.registry.update(
                job.job_id,
                status=jobs.FAILED,
                phase="Failed",
                error=result.error or "Ingest failed",
                source_id=result.source_id,
            )
            return

        jobs.registry.update(
            job.job_id,
            status=jobs.DONE,
            phase="Approved" if approve else "Indexed, awaiting approval",
            source_id=result.source_id,
            chunks_done=result.chunks_written,
            chunks_total=result.chunks_written,
        )

    # daemon: a shutdown should not be held open by an ingest that will be
    # restarted from scratch anyway.
    threading.Thread(target=_run, name=f"ingest-{job.job_id[:8]}", daemon=True).start()

    return IngestResponse(
        job_id=job.job_id,
        status=job.status,
        title=title,
        kind=extracted.kind,
        pages=extracted.pages,
    )


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    _: User | None = Depends(current_admin_user),
) -> JobStatus:
    """Progress for one ingest.

    404 also means "this process was restarted": jobs live in memory, so a
    restart takes the running thread with them. That is the truth rather than a
    lost record -- there is no work still going on behind it.
    """
    job = jobs.registry.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No such indexing job. If the server restarted, the upload "
                "stopped with it and needs to be retried."
            ),
        )
    return JobStatus(**job.as_dict())


@router.post("/sources/{source_id}/approval")
def set_source_approval(
    source_id: str,
    request: ApprovalRequest,
    _: User | None = Depends(current_admin_user),
) -> dict[str, Any]:
    """Approve or withdraw a source. Withdrawal takes effect immediately."""
    _enabled()
    set_approval(source_id, approved=request.approved)
    return {"source_id": source_id, "approved": request.approved}


@router.post("/sources/{source_id}/supersede")
def supersede_source(
    source_id: str,
    request: SupersedeRequest,
    _: User | None = Depends(current_admin_user),
) -> dict[str, Any]:
    """Make one version current. Older versions are kept, not deleted."""
    _enabled()
    supersede(source_id, keep_version=request.keep_version)
    return {"source_id": source_id, "current_version": request.keep_version}


@router.delete("/sources/{source_id}")
def remove_source(
    source_id: str,
    version: str | None = None,
    _: User | None = Depends(current_admin_user),
) -> dict[str, str]:
    """Delete a source's chunks. For a mistaken upload, not for supersession."""
    _enabled()
    delete_source(source_id, version=version)
    return {"source_id": source_id, "status": "deleted"}


@router.post("/search")
def test_search(
    query: str = Form(...),
    _: User | None = Depends(current_admin_user),
) -> SearchResponse:
    """Run a query and show the scores, including hits below the floor.

    This is the tuning tool for MIN_RETRIEVAL_SCORE. It bypasses the floor on
    purpose so a near-miss is visible; the agent still applies it.
    """
    _enabled()
    store = QdrantKnowledgeStore()
    try:
        candidates = store.candidates(query)
    except Exception as exc:  # noqa: BLE001
        return SearchResponse(
            query=query,
            hits=[],
            min_retrieval_score=config.MIN_RETRIEVAL_SCORE,
            unavailable=True,
            error=type(exc).__name__,
        )

    floor = config.MIN_RETRIEVAL_SCORE
    hits = [
        SearchHit(
            title=c.source.title,
            version=c.source.version,
            text=c.text[:400],
            score=round(c.score, 4),
            dense_score=round(c.dense_score, 4),
            sparse_score=round(c.sparse_score, 4),
            above_floor=c.score >= floor,
        )
        for c in candidates[: config.RETRIEVAL_TOP_K]
    ]
    best = max((c.score for c in candidates), default=0.0)
    return SearchResponse(
        query=query,
        hits=hits,
        min_retrieval_score=floor,
        best_score=round(best, 4),
        below_floor=bool(candidates) and best < floor,
    )
