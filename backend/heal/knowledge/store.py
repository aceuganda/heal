"""The knowledge store: one collection, one embedding model, one writer.

This is where the ranking rules in docs/architecture-decisions.md are actually
enforced, in this order:

  1. PRE-filter in Qdrant   approved == true AND current version, applied
                            BEFORE the ANN search. Post-filtering an HNSW
                            result set silently returns fewer than k and hides
                            the loss.
  2. hybrid score           dense cosine fused with sparse lexical overlap
  3. SCORE FLOOR            below MIN_RETRIEVAL_SCORE, return NOTHING. The old
                            pipeline always returned top-k regardless of
                            quality; for a dosage question a weak citation is
                            worse than an honest refusal.
  4. diversity cap          at most N chunks per source document
  5. context ordering       final order sets citation numbers

There is no reranker. See the plan for the trigger to add one.
"""
from typing import Any
from typing import Protocol

from heal import config
from heal.knowledge.embedder import Embedder
from heal.knowledge.embedder import get_embedder
from heal.knowledge.embedder import sparse_vector
from heal.knowledge.models import Chunk
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.models import SearchOutcome
from heal.knowledge.models import SourceRef
from heal.logger import get_logger

logger = get_logger(__name__)

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "lexical"


class KnowledgeStore(Protocol):
    """The seam. Swapping Qdrant for pgvector is an implementation of this."""

    def search(self, query: str, limit: int | None = None) -> SearchOutcome:
        ...


class QdrantKnowledgeStore:
    """Qdrant-backed store using named vectors for hybrid search.

    Named vectors from the first ingest, deliberately: adding a sparse vector
    to an existing single-vector collection means recreating it and re-embedding
    everything, so the shape is decided before any data exists.
    """

    def __init__(
        self,
        client: Any | None = None,
        embedder: Embedder | None = None,
        collection: str | None = None,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self.collection = collection or config.QDRANT_COLLECTION

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = build_client()
        return self._client

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def search(self, query: str, limit: int | None = None) -> SearchOutcome:
        """Retrieve approved chunks for an English query.

        Never raises at the caller: an unreachable store degrades to an empty
        outcome flagged `unavailable`, because a chat answer that says "I could
        not reach the library" is better than a 500.
        """
        want = limit if limit is not None else config.CONTEXT_TOP_K
        if not query.strip():
            return SearchOutcome()

        try:
            candidates = self._candidates(query)
        except Exception as exc:  # noqa: BLE001 -- degrade, never fail the chat
            logger.error("Knowledge store unavailable: %s", type(exc).__name__)
            return SearchOutcome(unavailable=True, error=type(exc).__name__)

        if not candidates:
            return SearchOutcome()

        best = max(c.score for c in candidates)
        kept = [c for c in candidates if c.score >= config.MIN_RETRIEVAL_SCORE]
        if not kept:
            # The near-miss is logged because it is what tunes the floor.
            logger.info(
                "All %d candidates below MIN_RETRIEVAL_SCORE (%.3f); best %.3f",
                len(candidates),
                config.MIN_RETRIEVAL_SCORE,
                best,
            )
            return SearchOutcome(best_score_before_floor=best, below_floor=True)

        return SearchOutcome(
            chunks=_cap_per_source(kept, config.MAX_CHUNKS_PER_SOURCE)[:want],
            best_score_before_floor=best,
        )

    def _candidates(self, query: str) -> list[RetrievedChunk]:
        """Fetch and fuse. Dense and sparse are searched separately, then merged."""
        from qdrant_client import models as qm

        top_k = config.RETRIEVAL_TOP_K
        # Applied before the ANN search, not after -- see the module docstring.
        approved_only = qm.Filter(
            must=[
                qm.FieldCondition(key="approved", match=qm.MatchValue(value=True)),
                qm.FieldCondition(key="is_current", match=qm.MatchValue(value=True)),
            ]
        )

        dense = self.client.search(
            collection_name=self.collection,
            query_vector=(DENSE_VECTOR, self.embedder.embed_query(query)),
            query_filter=approved_only,
            limit=top_k,
            with_payload=True,
        )
        results = {p.id: (_to_chunk(p), float(p.score), 0.0) for p in dense}

        if config.HYBRID_SEARCH:
            sparse = sparse_vector(query)
            if len(sparse):
                lexical = self.client.search(
                    collection_name=self.collection,
                    query_vector=qm.NamedSparseVector(
                        name=SPARSE_VECTOR,
                        vector=qm.SparseVector(
                            indices=sparse.indices, values=sparse.values
                        ),
                    ),
                    query_filter=approved_only,
                    limit=top_k,
                    with_payload=True,
                )
                for point in lexical:
                    chunk, dense_score, _ = results.get(
                        point.id, (_to_chunk(point), 0.0, 0.0)
                    )
                    results[point.id] = (chunk, dense_score, float(point.score))

        alpha = config.HYBRID_ALPHA if config.HYBRID_SEARCH else 1.0
        fused = [
            RetrievedChunk(
                chunk=chunk,
                score=alpha * dense_score + (1.0 - alpha) * _clamp(sparse_score),
                dense_score=dense_score,
                sparse_score=sparse_score,
            )
            for chunk, dense_score, sparse_score in results.values()
        ]
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused


def _clamp(score: float) -> float:
    """Sparse dot products are unbounded above; the fusion assumes 0..1."""
    return max(0.0, min(1.0, score))


def _cap_per_source(results: list[RetrievedChunk], cap: int) -> list[RetrievedChunk]:
    """At most `cap` chunks from any one document, order otherwise preserved.

    Stops a single long guideline from filling the whole context window and
    hiding a corroborating second source.
    """
    seen: dict[str, int] = {}
    kept: list[RetrievedChunk] = []
    for item in results:
        key = item.source.source_id
        if seen.get(key, 0) >= cap:
            continue
        seen[key] = seen.get(key, 0) + 1
        kept.append(item)
    return kept


def _to_chunk(point: Any) -> Chunk:
    payload = point.payload or {}
    return Chunk(
        chunk_id=str(point.id),
        text=payload.get("text", ""),
        ordinal=int(payload.get("ordinal", 0)),
        source=SourceRef(
            source_id=str(payload.get("source_id", "")),
            title=payload.get("title", "Untitled source"),
            version=str(payload.get("version", "1")),
            publisher=payload.get("publisher", ""),
            published=payload.get("published", ""),
        ),
    )


def list_sources(
    client: Any | None = None, collection: str | None = None
) -> list[dict[str, Any]]:
    """Every source in the collection, aggregated from its chunks.

    Reads Qdrant rather than PostgreSQL because Qdrant is currently the only
    store that holds sources at all -- see `docs/next-tasks.md` 1.2. When
    Postgres becomes the system of record this should read from there instead,
    and this function becomes the reconcile comparison.
    """
    client = client or build_client()
    name = collection or config.QDRANT_COLLECTION

    sources: dict[str, dict[str, Any]] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            key = f"{payload.get('source_id')}::{payload.get('version')}"
            entry = sources.setdefault(
                key,
                {
                    "source_id": payload.get("source_id", ""),
                    "title": payload.get("title", "Untitled"),
                    "version": str(payload.get("version", "1")),
                    "publisher": payload.get("publisher", ""),
                    "published": payload.get("published", ""),
                    "approved": bool(payload.get("approved", False)),
                    "is_current": bool(payload.get("is_current", True)),
                    "chunks": 0,
                },
            )
            entry["chunks"] += 1
            # A source counts as approved only if every chunk is. A partial
            # state means an approval half-applied, and should look wrong.
            entry["approved"] = entry["approved"] and bool(payload.get("approved"))
        if offset is None:
            break

    return sorted(sources.values(), key=lambda s: (s["title"].lower(), s["version"]))


def delete_source(
    source_id: str,
    version: str | None = None,
    client: Any | None = None,
    collection: str | None = None,
) -> None:
    """Remove a source's points. The only destructive operation in this module.

    Deleting is offered because an admin who uploads the wrong file needs to
    undo it. Superseding, not deleting, is the right move for guidance that has
    merely been replaced -- see `supersede()`.
    """
    from qdrant_client import models as qm

    client = client or build_client()
    must = [qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))]
    if version is not None:
        must.append(
            qm.FieldCondition(key="version", match=qm.MatchValue(value=version))
        )
    client.delete(
        collection_name=collection or config.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(filter=qm.Filter(must=must)),
    )
    logger.info("Deleted source=%s version=%s", source_id, version or "ALL")


def collection_stats(
    client: Any | None = None, collection: str | None = None
) -> dict[str, Any]:
    """Point counts and the tuning constants, for the admin status panel."""
    client = client or build_client()
    name = collection or config.QDRANT_COLLECTION
    info = client.get_collection(name)
    return {
        "collection": name,
        "points": getattr(info, "points_count", 0) or 0,
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": config.EMBEDDING_DIM,
        "hybrid_search": config.HYBRID_SEARCH,
        "hybrid_alpha": config.HYBRID_ALPHA,
        "retrieval_top_k": config.RETRIEVAL_TOP_K,
        "context_top_k": config.CONTEXT_TOP_K,
        "min_retrieval_score": config.MIN_RETRIEVAL_SCORE,
        "max_chunks_per_source": config.MAX_CHUNKS_PER_SOURCE,
    }


def build_client() -> Any:
    """Construct the Qdrant client from configuration.

    Refuses to connect without an API key: Qdrant's default setup has no
    authentication, so an unauthenticated store must be an explicit error
    rather than something reachable by accident.
    """
    from qdrant_client import QdrantClient

    url, api_key = config.require_knowledge_config()
    return QdrantClient(url=url, api_key=api_key, timeout=config.LLM_TIMEOUT)


def ensure_collection(client: Any | None = None, dimension: int | None = None) -> None:
    """Create the collection with both named vectors, if it does not exist.

    Idempotent, and never destructive: an existing collection is left exactly
    as it is. Re-shaping one means a new collection and a full re-embed, which
    is a deliberate operation, not a side effect of a service starting.
    """
    from qdrant_client import models as qm

    client = client or build_client()
    name = config.QDRANT_COLLECTION
    if client.collection_exists(name):
        logger.info("Qdrant collection %s already exists", name)
        return

    dim = dimension or config.EMBEDDING_DIM
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR: qm.VectorParams(size=dim, distance=qm.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR: qm.SparseVectorParams()},
    )
    # Indexed because every search filters on them before the ANN step; without
    # payload indexes that pre-filter degrades to a full scan.
    for field_name in ("approved", "is_current", "source_id"):
        client.create_payload_index(
            collection_name=name,
            field_name=field_name,
            field_schema=qm.PayloadSchemaType.BOOL
            if field_name != "source_id"
            else qm.PayloadSchemaType.KEYWORD,
        )
    logger.info("Created Qdrant collection %s (%d-dim dense + sparse)", name, dim)
