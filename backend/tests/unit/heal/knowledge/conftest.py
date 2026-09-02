"""Fakes for the retrieval tests.

Nothing here touches Qdrant, torch or the network. The store takes its client
and embedder as constructor arguments precisely so this is possible.
"""
from dataclasses import dataclass
from dataclasses import field
from types import SimpleNamespace
from typing import Any

import pytest

from heal import config


@dataclass
class FakePoint:
    """Stands in for a qdrant_client ScoredPoint."""

    id: str
    score: float
    payload: dict[str, Any]


@dataclass
class FakeQueryResponse:
    """`query_points` returns a wrapper; `search` returned a bare list."""

    points: list["FakePoint"]


@dataclass
class FakeCollectionInfo:
    """Just enough of CollectionInfo for `collection_uses_idf` to read it."""

    config: Any
    points_count: int

    @classmethod
    def build(cls, points: int, modifier: str | None) -> "FakeCollectionInfo":
        sparse = SimpleNamespace(modifier=modifier)
        return cls(
            config=SimpleNamespace(
                params=SimpleNamespace(sparse_vectors={"lexical": sparse})
            ),
            points_count=points,
        )


@dataclass
class FakeQdrant:
    """Records calls and returns scripted results.

    `dense_results` and `sparse_results` are returned for the two searches the
    store performs, so a test can make a chunk match lexically but not
    semantically -- which is the drug-code case the sparse half exists for.
    """

    dense_results: list[FakePoint] = field(default_factory=list)
    sparse_results: list[FakePoint] = field(default_factory=list)
    searches: list[dict[str, Any]] = field(default_factory=list)
    upserts: list[Any] = field(default_factory=list)
    payload_sets: list[dict[str, Any]] = field(default_factory=list)
    collections: set[str] = field(default_factory=set)
    raises: Exception | None = None
    # What `get_collection` reports the live sparse modifier to be. `None`
    # means a collection created before the modifier existed.
    live_modifier: str | None = None

    def query_points(self, **kwargs: Any) -> "FakeQueryResponse":
        """Mirrors the 1.19 client, which no longer has `search`.

        The old fake kept a `search` method after the real client dropped it,
        which is precisely the failure the `set_payload` note below describes:
        a fake that answers a call the server would refuse. Dense and sparse
        are told apart by `using`, the way the real API distinguishes them.
        """
        if self.raises:
            raise self.raises
        self.searches.append(kwargs)
        is_sparse = kwargs.get("using") == "lexical"
        return FakeQueryResponse(
            points=self.sparse_results if is_sparse else self.dense_results
        )

    def get_collection(self, name: str) -> "FakeCollectionInfo":
        return FakeCollectionInfo.build(
            points=len(self.dense_results), modifier=self.live_modifier
        )

    def upsert(self, *, collection_name: str, points: Any, **kwargs: Any) -> None:
        if self.raises:
            raise self.raises
        self.upserts.append({"collection_name": collection_name, "points": points})

    def set_payload(
        self,
        *,
        collection_name: str,
        payload: dict[str, Any],
        points: Any,
        **kwargs: Any
    ) -> None:
        """Mirrors the real signature deliberately.

        `set_payload` takes `points`; `delete` takes `points_selector`. A fake
        that swallowed **kwargs accepted the wrong name happily and every
        approval in the admin UI 500'd against a real Qdrant.
        """
        self.payload_sets.append(
            {"collection_name": collection_name, "payload": payload, "points": points}
        )

    def collection_exists(self, name: str) -> bool:
        return name in self.collections

    def create_collection(self, collection_name: str, **kwargs: Any) -> None:
        self.collections.add(collection_name)
        self.created = kwargs

    def create_payload_index(self, **kwargs: Any) -> None:
        pass


class FakeEmbedder:
    """Deterministic vectors, no model load."""

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension
        self.seen: list[str] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_query(self, text: str) -> list[float]:
        self.seen.append(text)
        return [0.1] * self._dimension

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.seen.extend(texts)
        return [[0.1] * self._dimension for _ in texts]


def make_point(
    point_id: str = "p1",
    score: float = 0.9,
    source_id: str = "src-1",
    title: str = "Uganda ART Guidelines",
    text: str = "Give TDF/3TC/DTG once daily.",
    version: str = "2022",
    ordinal: int = 0,
) -> FakePoint:
    return FakePoint(
        id=point_id,
        score=score,
        payload={
            "text": text,
            "ordinal": ordinal,
            "source_id": source_id,
            "title": title,
            "version": version,
            "publisher": "Ministry of Health",
            "published": "2022",
            "approved": True,
            "is_current": True,
        },
    )


@pytest.fixture
def fake_client() -> FakeQdrant:
    return FakeQdrant()


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture(autouse=True)
def predictable_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the tuning constants so tests assert behaviour, not today's defaults."""
    monkeypatch.setattr(config, "MIN_RETRIEVAL_SCORE", 0.35)
    monkeypatch.setattr(config, "MAX_CHUNKS_PER_SOURCE", 2)
    monkeypatch.setattr(config, "RETRIEVAL_TOP_K", 20)
    monkeypatch.setattr(config, "CONTEXT_TOP_K", 5)
    # Off by default in the suite so the existing assertions keep testing the
    # pre-IDF fusion, which is still a supported configuration. The IDF path
    # turns it on explicitly, so the change in scoring is asserted rather than
    # absorbed silently across every unrelated test.
    monkeypatch.setattr(config, "SPARSE_IDF", False)
    monkeypatch.setattr(config, "HYBRID_SEARCH", True)
    monkeypatch.setattr(config, "HYBRID_ALPHA", 0.6)
    monkeypatch.setattr(config, "QDRANT_COLLECTION", "test_collection")
