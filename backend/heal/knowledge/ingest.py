"""Getting approved material into the store.

One writer, triggered by a person. There is no scheduler, no crawler and no
connector: every run has a named actor recorded against it. That is the rule
that stops this growing back into the Danswer background fleet.

Order is fixed: chunk, embed, then write. Points are written with
`approved=False` unless the caller approves them explicitly, so uploading a
document is not the same act as endorsing it clinically.
"""
import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any

from heal import config
from heal.knowledge.chunking import split_text
from heal.knowledge.embedder import Embedder
from heal.knowledge.embedder import get_embedder
from heal.knowledge.embedder import sparse_vector
from heal.knowledge.models import SourceRef
from heal.knowledge.store import DENSE_VECTOR
from heal.knowledge.store import SPARSE_VECTOR
from heal.logger import get_logger

logger = get_logger(__name__)

# Guardrail against a mis-paste or a runaway extraction, not a policy limit.
MAX_DOCUMENT_CHARS = 5_000_000


@dataclass
class IngestResult:
    """The immutable record of one ingest run.

    Deliberately carries no document text and no patient text -- only counts,
    identifiers and versions. This is what `admin/jobs` reads.
    """

    source_id: str
    title: str
    version: str
    actor: str
    chunks_written: int = 0
    status: str = "completed"
    error: str | None = None
    model: str = ""
    started: str = ""
    finished: str = ""
    chunk_ids: list[str] = field(default_factory=list)


def reference_ingest(
    text: str,
    title: str,
    actor: str,
    client: Any | None = None,
    embedder: Embedder | None = None,
    source_id: str | None = None,
    version: str = "1",
    publisher: str = "",
    published: str = "",
    approved: bool = False,
    collection: str | None = None,
) -> IngestResult:
    """Chunk, embed and write one document. The only path that writes Qdrant.

    `approved=False` by default: a document has to be approved deliberately
    before any answer can cite it, because the retrieval filter requires it.
    """
    started = _now()
    source_id = source_id or str(uuid.uuid4())
    result = IngestResult(
        source_id=source_id,
        title=title,
        version=version,
        actor=actor,
        model=config.EMBEDDING_MODEL,
        started=started,
    )

    if not title.strip():
        return _failed(result, "Source title is required")
    if not actor.strip():
        # No anonymous writes. Every run is attributable.
        return _failed(result, "An actor is required: ingest is never anonymous")
    if len(text) > MAX_DOCUMENT_CHARS:
        return _failed(result, f"Document exceeds {MAX_DOCUMENT_CHARS} characters")

    chunks = split_text(text)
    if not chunks:
        return _failed(result, "Document produced no text to index")

    logger.info(
        "Ingest starting: source=%s version=%s chunks=%d actor=%s",
        source_id,
        version,
        len(chunks),
        actor,
    )

    try:
        embedder = embedder or get_embedder()
        vectors = embedder.embed_passages(chunks)
        client = client or _client()
        # The first upload into a fresh stack would otherwise fail on a missing
        # collection, which reads as "indexing is broken" rather than "nobody
        # ran the setup step". Creating it here is idempotent and never
        # destructive -- see ensure_collection.
        _ensure_collection(client)
        points = _build_points(
            chunks=chunks,
            vectors=vectors,
            source=SourceRef(
                source_id=source_id,
                title=title,
                version=version,
                publisher=publisher,
                published=published,
            ),
            approved=approved,
        )
        client.upsert(
            collection_name=collection or config.QDRANT_COLLECTION,
            points=points,
            wait=True,
        )
    except Exception as exc:  # noqa: BLE001 -- recorded, then surfaced to admin
        logger.error("Ingest failed for source=%s: %s", source_id, exc)
        return _failed(result, f"{type(exc).__name__}: {exc}")

    result.chunks_written = len(points)
    result.chunk_ids = [str(p.id) for p in points]
    result.finished = _now()
    logger.info(
        "Ingest completed: source=%s chunks=%d approved=%s",
        source_id,
        len(points),
        approved,
    )
    return result


def _build_points(
    chunks: list[str],
    vectors: list[list[float]],
    source: SourceRef,
    approved: bool,
) -> list[Any]:
    from qdrant_client import models as qm

    if len(chunks) != len(vectors):
        raise ValueError("Embedding returned a different number of vectors")

    points = []
    for ordinal, (text, dense) in enumerate(zip(chunks, vectors)):
        sparse = sparse_vector(text)
        points.append(
            qm.PointStruct(
                # Derived from source, version and position, so re-ingesting
                # the same version overwrites rather than duplicating.
                id=_point_id(source.source_id, source.version, ordinal),
                vector={
                    DENSE_VECTOR: dense,
                    SPARSE_VECTOR: qm.SparseVector(
                        indices=sparse.indices, values=sparse.values
                    ),
                },
                payload={
                    "text": text,
                    "ordinal": ordinal,
                    "source_id": source.source_id,
                    "title": source.title,
                    "version": source.version,
                    "publisher": source.publisher,
                    "published": source.published,
                    "approved": approved,
                    # Supersession is explicit, not time-decayed: a version is
                    # current or it is not. Clinical guidance is replaced, and
                    # a newer document is not automatically the right one.
                    "is_current": True,
                },
            )
        )
    return points


def supersede(
    source_id: str,
    keep_version: str,
    client: Any | None = None,
    collection: str | None = None,
) -> None:
    """Mark every other version of a source as no longer current.

    Nothing is deleted. Superseded points stay so an answer given last month
    can still be explained by the edition it was drawn from.
    """
    from qdrant_client import models as qm

    client = client or _client()
    # `points`, not `points_selector`: set_payload and delete take differently
    # named selector arguments, and the wrong one is a TypeError at runtime
    # rather than an import-time or type-check failure.
    client.set_payload(
        collection_name=collection or config.QDRANT_COLLECTION,
        payload={"is_current": False},
        points=qm.Filter(
            must=[
                qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))
            ],
            must_not=[
                qm.FieldCondition(
                    key="version", match=qm.MatchValue(value=keep_version)
                )
            ],
        ),
    )
    logger.info("Superseded source=%s, current version now %s", source_id, keep_version)


def set_approval(
    source_id: str,
    approved: bool,
    client: Any | None = None,
    collection: str | None = None,
) -> None:
    """Approve or unapprove every chunk of a source.

    This is the clinical gate. Retrieval pre-filters on it, so unapproving a
    source removes it from every future answer immediately.
    """
    from qdrant_client import models as qm

    client = client or _client()
    client.set_payload(
        collection_name=collection or config.QDRANT_COLLECTION,
        payload={"approved": approved},
        points=qm.Filter(
            must=[
                qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))
            ]
        ),
    )
    logger.info("Source %s approved=%s", source_id, approved)


def _point_id(source_id: str, version: str, ordinal: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}/{version}/{ordinal}"))


def _client() -> Any:
    from heal.knowledge.store import build_client

    return build_client()


def _ensure_collection(client: Any) -> None:
    from heal.knowledge.store import ensure_collection

    ensure_collection(client)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _failed(result: IngestResult, message: str) -> IngestResult:
    result.status = "failed"
    result.error = message
    result.finished = _now()
    logger.error("Ingest rejected: %s", message)
    return result
