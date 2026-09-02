"""Turning retrieved passages into citations the UI can open.

The chat UI has always expected two things on a message: `documents`, and a
`citations` map of `{marker number: document db id}`. It joins them to render
the reference list, and the drawer opens whatever the marker points at. Neither
was ever populated after retrieval was added, so every citation the model wrote
rendered as literal `[1]` text pointing at nothing.

This fills both, reusing the inherited `search_doc` table rather than adding
one. That table has been dormant since the connector fleet was retired, and its
columns are exactly what a retrieved passage needs: an identifier, a title, a
blurb, a score and the matched text.

Only markers the answer ACTUALLY used are persisted. The agent puts up to
CONTEXT_TOP_K passages in the prompt and the model routinely cites three of
five; storing the rest would show the reader sources the answer never leaned
on, which is worse than showing none.
"""
from typing import Any
from typing import TYPE_CHECKING

from heal.chat.external_refs import ExternalRef
from heal.knowledge.models import RetrievedChunk
from heal.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from heal_app.db.models import SearchDoc

logger = get_logger(__name__)

# How much of a passage to keep as the preview shown in the reference drawer.
# The full chunk is still in Qdrant; this is what renders without scrolling.
BLURB_CHARS = 400

# Metadata key marking a reference the model named rather than one retrieved
# from the approved library. Read by the drawer, which says so in as many
# words, and by the gloss endpoint, which refuses to summarise a source nobody
# fetched. A citation the reader cannot tell apart from an approved one is the
# failure this whole flag exists to prevent.
EXTERNAL_FLAG = "external_reference"


def select_cited(
    chunks: list[RetrievedChunk], cited_numbers: list[int]
) -> list[tuple[int, RetrievedChunk]]:
    """Pair each marker with the passage it points at, in citation order.

    Marker N is `chunks[N - 1]`: the prompt numbers passages from 1. A marker
    outside that range is dropped rather than trusted -- the model occasionally
    invents `[9]` when it was handed five passages, and a citation pointing at
    nothing is exactly what this path exists to prevent.

    Pure, and deliberately free of the ORM: this is the rule the whole
    reference UI rests on, so it must be testable without a database.
    """
    paired: list[tuple[int, RetrievedChunk]] = []
    for number in cited_numbers:
        index = number - 1
        if index < 0 or index >= len(chunks):
            logger.warning(
                "Answer cited [%d] but only %d passages were provided; dropping it",
                number,
                len(chunks),
            )
            continue
        paired.append((number, chunks[index]))
    return paired


def build_citations(
    db_session: "Session",
    chunks: list[RetrievedChunk],
    cited_numbers: list[int],
    external: dict[int, "ExternalRef"] | None = None,
) -> tuple[list["SearchDoc"], dict[int, str]]:
    """Store the cited passages and return them with a `{marker: id}` map.

    The rows are flushed, not committed. `create_new_chat_message` links them
    to the message and commits, so the answer and its citations land in one
    transaction -- an answer saved without them would cite nothing forever.

    `external` carries references the model NAMED when the library had no
    passage to give it (see heal/chat/external_refs.py). They are stored as
    rows so the same marker, the same drawer and the same map serve both kinds,
    but they are marked as what they are and carry no passage -- there is
    nothing behind them but a name. The two are mutually exclusive by
    construction: `external_refs.parse()` returns nothing when there were
    passages, because marker N would then already mean passage N.
    """
    from heal_app.db.models import SearchDoc

    docs: list[SearchDoc] = []
    citations: dict[int, str] = {}

    for number, chunk in select_cited(chunks, cited_numbers):
        search_doc = SearchDoc(**search_doc_fields(chunk))
        db_session.add(search_doc)
        db_session.flush()  # assigns the id the citation map points at
        docs.append(search_doc)
        # Stringified: the map is serialised to JSON, which has no UUID type.
        citations[number] = str(search_doc.id)

    for number in cited_numbers:
        ref = (external or {}).get(number)
        # `number in citations` cannot happen while the two kinds are exclusive,
        # but a library citation must win if that ever changes: it points at
        # words we hold, and the external one only at a name.
        if ref is None or number in citations:
            continue
        search_doc = SearchDoc(**external_doc_fields(ref))
        db_session.add(search_doc)
        db_session.flush()
        docs.append(search_doc)
        citations[number] = str(search_doc.id)

    return docs, citations


def search_doc_fields(chunk: RetrievedChunk) -> dict[str, Any]:
    """Map a retrieved passage onto the inherited SearchDoc columns.

    Returns a plain dict rather than the model so the mapping can be tested
    without importing the ORM.
    """
    source = chunk.source
    return {
        # Version is part of the identity: two editions of one guideline are
        # different sources, and a reader has to be able to tell which was used.
        "document_id": f"{source.source_id}:{source.version}",
        "chunk_ind": chunk.chunk.ordinal,
        "semantic_id": source.label(),
        "link": None,
        "blurb": chunk.text[:BLURB_CHARS],
        "boost": 0,
        "source_type": _file_source(),
        "hidden": False,
        "doc_metadata": _metadata(chunk),
        "score": chunk.score,
        # The passage itself, which is what the drawer shows and what the
        # plain-language gloss is generated from.
        "match_highlights": [chunk.text],
        "updated_at": None,
        "primary_owners": None,
        "secondary_owners": None,
    }


def external_doc_fields(ref: "ExternalRef") -> dict[str, Any]:
    """Map a model-named reference onto the same columns, marked as external.

    Deliberately empty where a library citation has substance. `blurb` and
    `match_highlights` are blank because there IS no passage: nothing was
    retrieved, nothing was read, and a "relevant excerpt" here would be text
    the model wrote about a document it did not open. `link` is null for the
    same reason -- a URL nobody fetched is a claim about what is at the other
    end of it.

    `EXTERNAL_FLAG` in the metadata is what the drawer reads to say so, and
    what `/chat/reference/{id}/gloss` reads to refuse to summarise it.
    """
    return {
        "document_id": f"external:{ref.name.lower()[:120]}",
        "chunk_ind": 0,
        "semantic_id": ref.name,
        "link": None,
        "blurb": "",
        "boost": 0,
        "source_type": _file_source(),
        "hidden": False,
        "doc_metadata": {EXTERNAL_FLAG: "true"},
        # Zero, because the column is NOT NULL and there is no honest number to
        # put here: this was never ranked against anything. The drawer reads
        # the external flag, not the score, so nothing displays it as a
        # relevance of nil.
        "score": 0.0,
        "match_highlights": [],
        "updated_at": None,
        "primary_owners": None,
        "secondary_owners": None,
    }


def _file_source() -> Any:
    """An uploaded document. Imported lazily to keep this module ORM-free."""
    from heal_app.configs.constants import DocumentSource

    return DocumentSource.FILE


def _metadata(chunk: RetrievedChunk) -> dict[str, Any]:
    """Everything an admin needs to explain why this passage was cited."""
    source = chunk.source
    meta = {
        "source_id": source.source_id,
        "version": str(source.version),
        "dense_score": f"{chunk.dense_score:.4f}",
        "sparse_score": f"{chunk.sparse_score:.4f}",
    }
    if source.publisher:
        meta["publisher"] = source.publisher
    if source.published:
        meta["published"] = str(source.published)
    return meta
