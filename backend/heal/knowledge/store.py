"""The knowledge store: one collection, one embedding model, one writer.

This is where the ranking rules in docs/architecture-decisions.md are actually
enforced, in this order:

  1. PRE-filter in Qdrant   approved == true AND current version, applied
                            BEFORE the ANN search. Post-filtering an HNSW
                            result set silently returns fewer than k and hides
                            the loss.
  2. hybrid score           dense cosine fused with sparse lexical overlap.
                            The sparse half is weighted by inverse document
                            frequency computed inside Qdrant (SPARSE_IDF), so
                            a rare drug code outranks a ubiquitous word. IDF
                            is a property of the COLLECTION, fixed at
                            creation -- see `ensure_collection`.
  3. SCORE FLOOR            below MIN_RETRIEVAL_SCORE, return NOTHING. The old
                            pipeline always returned top-k regardless of
                            quality; for a dosage question a weak citation is
                            worse than an honest refusal.
  4. diversity cap          at most N chunks per source document
  5. context ordering       final order sets citation numbers

There is no reranker. See the plan for the trigger to add one.

Everything here runs on ENGLISH text. A Luganda question is translated to
English before it reaches this module and the answer is translated back
afterwards, so queries, chunks, lexical matching and every score in between are
English throughout. Nothing downstream should re-derive a score from translated
text.

The tuning constants reach this module as a `RetrievalSettings` value rather
than being read from `heal.config` in place. Omitting it reads exactly the same
constants, so the chat path is unchanged; passing one lets the admin playground
try a different floor for a single request without touching what any concurrent
conversation sees. See heal/knowledge/settings.py.
"""
from dataclasses import dataclass
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
from heal.knowledge.settings import RetrievalSettings
from heal.logger import get_logger

logger = get_logger(__name__)

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "lexical"


class KnowledgeStore(Protocol):
    """The seam. Swapping Qdrant for pgvector is an implementation of this."""

    def search(
        self,
        query: str,
        limit: int | None = None,
        lexical_query: str | None = None,
        settings: RetrievalSettings | None = None,
    ) -> SearchOutcome:
        ...

    def candidates(
        self,
        query: str,
        lexical_query: str | None = None,
        settings: RetrievalSettings | None = None,
    ) -> list[RetrievedChunk]:
        """Ranked hits with nothing discarded yet.

        Part of the seam rather than an implementation detail: the admin
        surfaces exist to show what the floor and the cap are about to throw
        away, and a store that could not report that would be unusable behind
        them.
        """
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

    def search(
        self,
        query: str,
        limit: int | None = None,
        lexical_query: str | None = None,
        settings: RetrievalSettings | None = None,
    ) -> SearchOutcome:
        """Retrieve approved chunks for an English query.

        `query` is embedded; `lexical_query`, when given, is what the sparse
        half matches on. They differ when the question has been rewritten for
        retrieval and the user's literal wording still has to match.

        `settings` is one request's tuning. Omitted, it reads the deployment's
        own constants, which is what every chat turn does.

        Never raises at the caller: an unreachable store degrades to an empty
        outcome flagged `unavailable`, because a chat answer that says "I could
        not reach the library" is better than a 500.
        """
        settings = settings or RetrievalSettings()
        want = limit if limit is not None else settings.context_top_k
        if not query.strip():
            return SearchOutcome()

        try:
            candidates = self.candidates(query, lexical_query, settings)
        except Exception as exc:  # noqa: BLE001 -- degrade, never fail the chat
            logger.error("Knowledge store unavailable: %s", type(exc).__name__)
            return SearchOutcome(unavailable=True, error=type(exc).__name__)

        if not candidates:
            return SearchOutcome()

        best = max(c.score for c in candidates)
        selection = select_context(candidates, settings, limit=want)
        if not selection.above_floor:
            # The near-miss is logged because it is what tunes the floor.
            logger.info(
                "All %d candidates below MIN_RETRIEVAL_SCORE (%.3f); best %.3f",
                len(candidates),
                settings.min_retrieval_score,
                best,
            )
            return SearchOutcome(best_score_before_floor=best, below_floor=True)

        return SearchOutcome(
            chunks=selection.context,
            best_score_before_floor=best,
        )

    def candidates(
        self,
        query: str,
        lexical_query: str | None = None,
        settings: RetrievalSettings | None = None,
    ) -> list[RetrievedChunk]:
        """Fetch and fuse. Dense and sparse are searched separately, then merged.

        `lexical_query` feeds only the sparse half. It exists so the caller can
        embed a cleaned-up question while still matching literally on what the
        health worker actually typed -- see `Understanding.lexical_query`.

        Returns every candidate, unfiltered: the floor and the diversity cap are
        applied afterwards by `select_context`. That split is what lets an admin
        see the near-misses a floor is about to discard.
        """
        from qdrant_client import models as qm

        settings = settings or RetrievalSettings()
        top_k = settings.retrieval_top_k
        # Applied before the ANN search, not after -- see the module docstring.
        approved_only = qm.Filter(
            must=[
                qm.FieldCondition(key="approved", match=qm.MatchValue(value=True)),
                qm.FieldCondition(key="is_current", match=qm.MatchValue(value=True)),
            ]
        )

        # `query_points`, not `search`: the latter was removed in the 1.19
        # client. It is also the endpoint that carries server-side fusion, so
        # moving to it now is what makes RRF available later without a second
        # rewrite of this function.
        dense = self.client.query_points(
            collection_name=self.collection,
            query=self.embedder.embed_query(query),
            using=DENSE_VECTOR,
            query_filter=approved_only,
            limit=top_k,
            with_payload=True,
        ).points
        results = {p.id: (_to_chunk(p), float(p.score), 0.0) for p in dense}

        if settings.hybrid_search:
            sparse = sparse_vector(lexical_query or query)
            if len(sparse):
                lexical = self.client.query_points(
                    collection_name=self.collection,
                    query=qm.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE_VECTOR,
                    query_filter=approved_only,
                    limit=top_k,
                    with_payload=True,
                ).points
                for point in lexical:
                    chunk, dense_score, _ = results.get(
                        point.id, (_to_chunk(point), 0.0, 0.0)
                    )
                    results[point.id] = (chunk, dense_score, float(point.score))

        alpha = settings.alpha
        rows = list(results.values())
        scale = _sparse_scale(rows)
        fused = [
            RetrievedChunk(
                chunk=chunk,
                score=alpha * dense_score
                + (1.0 - alpha) * _normalise_sparse(sparse_score, scale),
                dense_score=dense_score,
                sparse_score=sparse_score,
            )
            for chunk, dense_score, sparse_score in rows
        ]
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused


@dataclass(frozen=True)
class Selection:
    """What each stage of the filter did to a candidate list.

    `context` is what reaches the prompt. The two id sets exist so a caller can
    explain a candidate's fate rather than merely observing that it vanished --
    "0.34, one hundredth under the floor" and "cut because two better chunks
    from the same guideline came first" are different problems with different
    fixes, and an admin tuning the floor has to be able to tell them apart.
    """

    above_floor: list[RetrievedChunk]
    context: list[RetrievedChunk]
    passed_floor: frozenset[str]
    survived_cap: frozenset[str]


def select_context(
    candidates: list[RetrievedChunk],
    settings: RetrievalSettings,
    limit: int | None = None,
) -> Selection:
    """Apply the score floor, then the diversity cap, then the context size.

    The single implementation of stages 3-5 in the module docstring. The chat
    path and the admin playground both go through it, so a playground result
    cannot describe a pipeline the health worker's answer did not run.
    """
    want = limit if limit is not None else settings.context_top_k
    above_floor = [c for c in candidates if c.score >= settings.min_retrieval_score]
    capped = _cap_per_source(above_floor, settings.max_chunks_per_source)
    return Selection(
        above_floor=above_floor,
        context=capped[:want],
        passed_floor=frozenset(c.chunk.chunk_id for c in above_floor),
        survived_cap=frozenset(c.chunk.chunk_id for c in capped),
    )


def _clamp(score: float) -> float:
    """Sparse dot products are unbounded above; the fusion assumes 0..1."""
    return max(0.0, min(1.0, score))


def _sparse_scale(rows: list[tuple[Chunk, float, float]]) -> float:
    """The divisor that puts this result set's sparse scores back into 0..1.

    Without IDF the sparse score is a cosine between two L2-normalised term
    frequency vectors, already in 0..1, and clamping is enough. That is the
    pre-IDF behaviour and it is preserved exactly.

    With IDF the server multiplies each term by roughly log(N / df), so a rare
    drug code can carry a weight of 8 or more and the dot product routinely
    exceeds 1. Clamping there would be actively harmful: nearly every lexical
    hit would saturate at 1.0, every sparse score would become identical, and
    the ordering the IDF weighting was added to produce would be thrown away at
    the last step. Dividing by the best score in the same result set keeps the
    ordering intact and bounded.

    The honest caveat: this makes the sparse half a RELATIVE measure -- the
    strongest lexical match in a result set always contributes the full
    `1 - alpha`, whether it is a superb match or a mediocre one. That shifts
    what a fused score means, and therefore what MIN_RETRIEVAL_SCORE means. See
    `collection_stats`, which reports the combination so the mismatch is
    visible rather than assumed away.
    """
    if not config.SPARSE_IDF:
        return 1.0
    best = max((sparse for _, _, sparse in rows), default=0.0)
    return best if best > 0.0 else 1.0


def _normalise_sparse(score: float, scale: float) -> float:
    """One sparse score on the 0..1 scale the fusion weight assumes."""
    return _clamp(score / scale) if scale > 0.0 else 0.0


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

    # An empty library and an uncreated collection look the same to an admin,
    # and neither is an error worth a 500 on a freshly started stack.
    if not client.collection_exists(name):
        return []

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
    exists = client.collection_exists(name)
    info = client.get_collection(name) if exists else None
    # Configured and live are reported separately on purpose. They disagree
    # whenever the flag was turned on after the collection was built, and an
    # admin reading a panel that showed only the flag would believe rare drug
    # codes were being weighted when they were not.
    live_idf = collection_uses_idf(client, name) if exists else None
    return {
        "collection": name,
        "collection_exists": exists,
        "points": (getattr(info, "points_count", 0) or 0) if info else 0,
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": config.EMBEDDING_DIM,
        "hybrid_search": config.HYBRID_SEARCH,
        "hybrid_alpha": config.HYBRID_ALPHA,
        "sparse_idf_configured": config.SPARSE_IDF,
        "sparse_idf_active": live_idf,
        "sparse_idf_needs_reingest": bool(config.SPARSE_IDF and live_idf is False),
        "retrieval_top_k": config.RETRIEVAL_TOP_K,
        "context_top_k": config.CONTEXT_TOP_K,
        "min_retrieval_score": config.MIN_RETRIEVAL_SCORE,
        # True whenever the floor is being applied to a score distribution it
        # was never derived against. Both halves are unmeasured today, so this
        # is honest rather than alarming -- but it has to be visible.
        "min_retrieval_score_unvalidated": True,
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


def collection_uses_idf(client: Any, collection: str) -> bool | None:
    """Whether the LIVE collection applies IDF. None when it cannot be read.

    Read from the server rather than inferred from config, because the two can
    disagree: the modifier is fixed when the collection is created, so setting
    `HEAL_SPARSE_IDF=true` against a collection built without it changes
    nothing at all. Everything that reports on retrieval needs to be able to
    tell the difference between "IDF is on" and "IDF is configured on".
    """
    try:
        info = client.get_collection(collection)
        params = info.config.params.sparse_vectors[SPARSE_VECTOR]
        modifier = getattr(params, "modifier", None)
        return str(getattr(modifier, "value", modifier)).lower() == "idf"
    except Exception:  # noqa: BLE001 -- a status probe must not raise
        return None


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
        # The one case worth more than an "already exists" line. The IDF
        # modifier can only be set at creation, so a collection built before
        # this change will keep scoring without corpus statistics no matter
        # what the config says -- silently, and while the admin panel claims
        # the setting is on. Saying so here is what stops that going unnoticed.
        live = collection_uses_idf(client, name)
        if config.SPARSE_IDF and live is False:
            logger.warning(
                "Qdrant collection %s was created WITHOUT the IDF modifier, but "
                "HEAL_SPARSE_IDF is on. Lexical scoring is still running on raw "
                "term frequency and rare drug codes remain under-weighted. "
                "Recreate the collection and re-ingest the corpus to apply it.",
                name,
            )
        else:
            logger.info("Qdrant collection %s already exists", name)
        return

    dim = dimension or config.EMBEDDING_DIM
    # IDF is a property of the collection, applied by Qdrant at query time to
    # the raw term frequencies we write. Nothing changes on the ingest side.
    sparse_params = (
        qm.SparseVectorParams(modifier=qm.Modifier.IDF)
        if config.SPARSE_IDF
        else qm.SparseVectorParams()
    )
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR: qm.VectorParams(size=dim, distance=qm.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR: sparse_params},
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
    logger.info(
        "Created Qdrant collection %s (%d-dim dense + sparse, IDF %s)",
        name,
        dim,
        "on" if config.SPARSE_IDF else "off",
    )
