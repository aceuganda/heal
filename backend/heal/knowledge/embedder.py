"""Turning text into the two vectors a hybrid search needs.

Dense: `thenlper/gte-small`, 384 dimensions, English. Loaded lazily and cached,
because importing sentence-transformers costs seconds and nothing that merely
*mentions* embedding should pay that.

Sparse: a hashed bag of lexical terms, computed here rather than by a model.
This is the cheap answer to ranking risk #1. Pure dense retrieval is weakest
exactly where this product is most sensitive -- "TDF/3TC/DTG", "500mg BD", ICD
codes -- because those are strings to match, not concepts to embed. A sparse
vector alongside the dense one recovers that without a second service.
"""
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from heal import config
from heal.logger import get_logger

logger = get_logger(__name__)

# Sparse vector index space. Large enough that collisions between clinical
# terms are rare, small enough to stay cheap.
SPARSE_DIM = 2**20

# Tokens keep digits, and keep '/' '-' '+' inside a token, so "TDF/3TC/DTG",
# "co-trimoxazole" and "500mg" survive as single searchable units instead of
# being shredded into meaningless fragments.
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[/\-+][A-Za-z0-9]+)*")

# Words too common to carry retrieval signal. Deliberately tiny: an aggressive
# clinical stop list risks dropping a term that matters ("no", "not", "without"
# change a dose instruction completely).
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    to was were will with this these those which what when how why do does did
    can could should would you your i we they he she them their there here""".split()
)


@dataclass(frozen=True)
class SparseVector:
    """Qdrant's sparse form: parallel index and value arrays."""

    indices: list[int]
    values: list[float]

    def __len__(self) -> int:
        return len(self.indices)


class Embedder(Protocol):
    """What the store needs. A fake satisfying this is enough to test search."""

    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    def dimension(self) -> int:
        ...


def tokenize(text: str) -> list[str]:
    """Lowercased lexical tokens, clinical identifiers kept intact."""
    return [
        token
        for raw in _TOKEN.findall(text.lower())
        if (token := raw) and token not in _STOPWORDS and len(token) > 1
    ]


def sparse_vector(text: str) -> SparseVector:
    """Hashed term-frequency vector with sublinear damping.

    Sublinear (1 + log tf) rather than raw counts so a term repeated twenty
    times in a long guideline does not swamp a rarer term that actually
    distinguishes the passage.

    Weights are accumulated PER INDEX, not per token. Two different tokens can
    hash to the same slot -- that is inherent to the hashing trick, not a bug --
    and emitting one entry each produced a duplicate index. Qdrant rejects that
    outright:

        422 ... points[11].vector.?.indices: must be unique

    which failed the whole write. Summing the colliding weights is also the
    correct reading: they are the same feature as far as the vector is
    concerned.
    """
    counts = Counter(tokenize(text))
    if not counts:
        return SparseVector(indices=[], values=[])

    weights: dict[int, float] = {}
    for token, count in counts.items():
        index = _hash_token(token)
        weights[index] = weights.get(index, 0.0) + 1.0 + math.log(count)

    pairs = sorted(weights.items())
    norm = math.sqrt(sum(v * v for _, v in pairs)) or 1.0
    return SparseVector(
        indices=[i for i, _ in pairs],
        values=[v / norm for _, v in pairs],
    )


def _hash_token(token: str) -> int:
    """Stable across processes and restarts -- unlike Python's hash()."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % SPARSE_DIM


class SentenceTransformerEmbedder:
    """The real dense embedder. Loads the model on first use, then caches it."""

    def __init__(self, model_name: str | None = None, dimension: int | None = None):
        self.model_name = model_name or config.EMBEDDING_MODEL
        self._dimension = dimension or config.EMBEDDING_DIM
        self._model: object | None = None

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self.model_name)
            model = SentenceTransformer(self.model_name)
            actual = model.get_sentence_embedding_dimension()
            if actual != self._dimension:
                # Fail loudly. A silent mismatch writes unsearchable points
                # into the collection and is only noticed as bad answers.
                raise ValueError(
                    f"{self.model_name} produces {actual}-dim vectors but "
                    f"HEAL_EMBEDDING_DIM is {self._dimension}. The dimension is "
                    "frozen before first ingest: changing it needs a new "
                    "collection and a full re-embed."
                )
            self._model = model
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(  # type: ignore[attr-defined]
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [list(map(float, v)) for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_passages([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformerEmbedder:
    """Process-wide embedder. One model in memory, not one per request."""
    return SentenceTransformerEmbedder()
