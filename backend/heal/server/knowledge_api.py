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
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from pydantic import BaseModel

from heal import config
from heal.knowledge import extract as extraction
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
    status: str
    source_id: str
    title: str
    version: str
    chunks_written: int
    approved: bool
    kind: str = "text"
    pages: int = 0
    error: str | None = None


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
    """Every route needs the store; say plainly when it is switched off."""
    if not config.KNOWLEDGE_ENABLED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Knowledge retrieval is disabled. Start the stack with "
                "`make kb-up` (KNOWLEDGE_ENABLED=true) to manage sources."
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
    """Upload, extract, chunk, embed and store one document.

    Unapproved unless `approve` is set: retrieval filters on approval, so a
    document uploaded here cannot be cited until someone endorses it.
    """
    _enabled()

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    try:
        extracted = extraction.extract(data, file.filename or "upload")
    except extraction.ExtractionError as exc:
        # 422, not 500: the file is the problem and the message says how.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The actor is recorded on the run. Ingest refuses to be anonymous, and
    # with auth disabled there is no user, so the fallback is explicit rather
    # than silently blank.
    actor = getattr(user, "email", None) or "local-admin"

    result = reference_ingest(
        text=extracted.text,
        title=title,
        actor=actor,
        version=version,
        publisher=publisher,
        published=published,
        approved=approve,
    )
    if result.status == "failed":
        raise HTTPException(status_code=400, detail=result.error or "Ingest failed")

    return IngestResponse(
        status=result.status,
        source_id=result.source_id,
        title=result.title,
        version=result.version,
        chunks_written=result.chunks_written,
        approved=approve,
        kind=extracted.kind,
        pages=extracted.pages,
    )


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
        candidates = store._candidates(query)
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
