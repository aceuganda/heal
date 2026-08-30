"""Types crossing the retrieval boundary.

Plain dataclasses on purpose: nothing here should drag in Qdrant, torch or
SQLAlchemy, so the agent, the prompt builder and their tests can import these
without any of that being installed.
"""
from dataclasses import dataclass
from dataclasses import field


@dataclass(frozen=True)
class SourceRef:
    """Where a chunk came from, as it will be shown to a health worker.

    `version` matters clinically: guidance is superseded, not decayed. A chunk
    carries the version it was approved under so an answer can be traced to the
    edition it came from.
    """

    source_id: str
    title: str
    version: str = "1"
    publisher: str = ""
    published: str = ""

    def label(self) -> str:
        """Human-readable citation label."""
        parts = [self.title]
        if self.publisher:
            parts.append(self.publisher)
        if self.published:
            parts.append(self.published)
        return " — ".join(parts)


@dataclass(frozen=True)
class Chunk:
    """One embeddable passage, before it has been searched for."""

    chunk_id: str
    source: SourceRef
    text: str
    # Position within the source document, used for stable ordering and for
    # showing neighbouring text in the admin source browser.
    ordinal: int = 0


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk that came back from a search, with why it came back."""

    chunk: Chunk
    score: float
    # Which half of the hybrid search found it. Useful when debugging a miss:
    # a drug code that only ever matches lexically is a different problem from
    # one that matches semantically but ranks low.
    dense_score: float = 0.0
    sparse_score: float = 0.0

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def source(self) -> SourceRef:
        return self.chunk.source


@dataclass
class SearchOutcome:
    """The result of one retrieval, including the reason it may be empty.

    An empty list is not self-explanatory: "nothing was approved yet", "the
    store is unreachable" and "everything scored below the floor" need
    different responses from the agent, and different things said to the user.
    """

    chunks: list[RetrievedChunk] = field(default_factory=list)
    # Highest score seen before the floor was applied. Lets an operator see how
    # close a refusal was, which is what tunes MIN_RETRIEVAL_SCORE.
    best_score_before_floor: float = 0.0
    below_floor: bool = False
    unavailable: bool = False
    error: str | None = None

    def __bool__(self) -> bool:
        """Truthy only when chunks came back.

        Note for callers: an outcome carrying `unavailable` or `below_floor` is
        still falsy, so `outcome or SearchOutcome()` DISCARDS the reason it was
        empty. Use an explicit `is None` check when defaulting.
        """
        return bool(self.chunks)

    @property
    def sources(self) -> list[SourceRef]:
        """Distinct sources, in citation order."""
        seen: dict[str, SourceRef] = {}
        for item in self.chunks:
            seen.setdefault(item.source.source_id, item.source)
        return list(seen.values())
