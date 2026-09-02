"""Environment-driven configuration for Heal modules.

Rule: no network address is ever written in source. Every host, port and key is
read from the environment so that deployments can be moved, rotated or made
private without a code change. Missing values fail loudly at call time with an
actionable message rather than falling back to a shared default.
"""
import os


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


#####
# Translation services
#
# Heal runs two private machine-translation services: one Luganda->English, one
# English->Luganda. Under Design A these are the only models Luganda text ever
# touches -- retrieval and generation happen entirely in English.
#####

# Provider implementation to use. "heal_mt" is the private MT pair; other
# providers can be registered without touching call sites.
TRANSLATION_PROVIDER = _env_str("TRANSLATION_PROVIDER", "heal_mt")

# Base URLs, no trailing slash. Required when the heal_mt provider is active.
TRANSLATION_EN_URL = _env_str("TRANSLATION_EN_URL").rstrip("/")
TRANSLATION_LUG_URL = _env_str("TRANSLATION_LUG_URL").rstrip("/")

# Optional bearer token, sent to both services. The current deployment has no
# auth at all; this exists so that turning it on is a config change.
TRANSLATION_API_KEY = _env_str("TRANSLATION_API_KEY")

# The old code had no timeout, so a hung MT service hung the whole chat request.
TRANSLATION_CONNECT_TIMEOUT = _env_float("TRANSLATION_CONNECT_TIMEOUT", 5.0)
TRANSLATION_READ_TIMEOUT = _env_float("TRANSLATION_READ_TIMEOUT", 60.0)

# Retries apply to connection-level failures only, never to a partially
# streamed response -- replaying one would duplicate text in the user's answer.
TRANSLATION_MAX_RETRIES = _env_int("TRANSLATION_MAX_RETRIES", 2)
TRANSLATION_RETRY_BACKOFF = _env_float("TRANSLATION_RETRY_BACKOFF", 0.5)

# Per-token pacing when streaming a translation to the browser. Purely cosmetic:
# it keeps the Luganda answer arriving at a readable speed rather than in one
# burst. Set to 0 to disable.
TRANSLATION_STREAM_DELAY = _env_float("TRANSLATION_STREAM_DELAY", 0.09)


#####
# Chat model selection
#
# The chat model is chosen by id from the catalogue in heal/llm/registry.py
# rather than by editing call sites, so that trying a different model is a
# config change and the admin UI has something to list.
#####

# Default model id. Must exist in the catalogue.
CHAT_MODEL = _env_str("HEAL_CHAT_MODEL", "gpt-4o-mini")

# Cheaper/faster model used for classification and other short internal calls.
CLASSIFIER_MODEL = _env_str("HEAL_CLASSIFIER_MODEL", "gpt-4o-mini")

# Comma-separated allowlist of model ids offered to users. Empty means "every
# model in the catalogue whose provider is configured".
ENABLED_CHAT_MODELS = _env_str("HEAL_ENABLED_CHAT_MODELS")

# Seconds before an LLM call is abandoned.
LLM_TIMEOUT = _env_int("HEAL_LLM_TIMEOUT", 60)


#####
# Knowledge / retrieval
#
# On by default. Retrieval is the product: a stack that boots unable to index
# or cite a document is broken, not configured. The flag remains so a
# deployment without a vector store can still answer from the model alone --
# `false` reproduces the pre-retrieval behaviour exactly.
#####

KNOWLEDGE_ENABLED = _env_str("KNOWLEDGE_ENABLED", "true").lower() == "true"

# Qdrant connection. Read only on the retrieval path; the compose files set it
# to the internal service name.
QDRANT_URL = _env_str("QDRANT_URL").rstrip("/")

# Qdrant's default setup has no authentication at all. Heal requires a key
# rather than treating it as optional, so an unauthenticated vector store
# cannot be reached by accident.
QDRANT_API_KEY = _env_str("QDRANT_API_KEY")

# Collection name. Changing the embedding dimension means a new collection and
# a full re-embed, so the name carries the dimension (D6 freezes it at 384).
QDRANT_COLLECTION = _env_str("QDRANT_COLLECTION", "heal_reference_384")

# Embedding model. English-only under Design A, so it does not need to be
# multilingual -- Luganda is translated upstream and never reaches this.
EMBEDDING_MODEL = _env_str("HEAL_EMBEDDING_MODEL", "thenlper/gte-small")

# Frozen before first ingest (D6). Changing it means a new collection and a
# full re-embed, which is why it is asserted against the model at startup
# rather than trusted.
EMBEDDING_DIM = _env_int("HEAL_EMBEDDING_DIM", 384)

# Candidates fetched from Qdrant before filtering.
RETRIEVAL_TOP_K = _env_int("HEAL_RETRIEVAL_TOP_K", 20)

# Chunks actually placed in the prompt.
CONTEXT_TOP_K = _env_int("HEAL_CONTEXT_TOP_K", 5)

# Score floor. Below this the store returns nothing and the agent says it has
# no approved source rather than citing weak text under a citation marker that
# lends it false authority.
#
# This is a CLINICAL SAFETY PARAMETER, not a tuning knob. The default is a
# placeholder: it must be set from measured results on the clinician eval set
# before any real deployment. Recorded in the repo when it is.
MIN_RETRIEVAL_SCORE = _env_float("HEAL_MIN_RETRIEVAL_SCORE", 0.35)

# Diversity cap: at most this many chunks from any one source document, so a
# single long guideline cannot crowd out a corroborating second source.
MAX_CHUNKS_PER_SOURCE = _env_int("HEAL_MAX_CHUNKS_PER_SOURCE", 2)

# Hybrid search. Dense alone is weakest exactly where this product is most
# sensitive -- drug codes, abbreviations and dosages ("TDF/3TC/DTG", "500mg
# BD"). A sparse lexical vector alongside the dense one covers that without a
# second service and without a 2.3 GB multi-vector model.
HYBRID_SEARCH = _env_str("HEAL_HYBRID_SEARCH", "true").lower() == "true"

# Weight of the dense score when fusing dense and sparse results. 1.0 is
# dense-only; 0.0 is lexical-only.
#
# NOTE: this constant was derived when the sparse half was raw term frequency.
# With SPARSE_IDF on, the sparse score changes scale, and the fusion normalises
# it per result set to keep this weight meaningful. See `_normalise_sparse`.
HYBRID_ALPHA = _env_float("HEAL_HYBRID_ALPHA", 0.6)

# Inverse document frequency for the sparse half, computed by Qdrant itself.
#
# Without it, a term is weighted only by how often it appears in ITS OWN chunk.
# `TDF/3TC/DTG` -- rare, and therefore the most discriminating token in an ART
# question -- is then weighted no more heavily than `patient`, which is in
# nearly every chunk. The lexical stage exists to catch drug codes and was
# quietly under-weighting exactly those. See "The IDF gap" in
# docs/architecture-decisions.md.
#
# The modifier is fixed at COLLECTION CREATION. Turning this on for a
# collection that was built without it changes nothing except the log line
# `ensure_collection` writes to say so: the collection must be rebuilt and the
# corpus re-ingested. That is why this is a config flag and not a silent
# default -- the operator has to know a re-ingest is part of the change.
SPARSE_IDF = _env_str("HEAL_SPARSE_IDF", "true").lower() == "true"

# Chunking. Characters, not tokens: the boundary only has to be stable and
# explainable, and a character window needs no tokenizer at ingest time.
CHUNK_SIZE = _env_int("HEAL_CHUNK_SIZE", 1200)
CHUNK_OVERLAP = _env_int("HEAL_CHUNK_OVERLAP", 200)

# Chunks embedded and written per batch during ingest.
#
# This is the granularity of both progress reporting and crash loss: a smaller
# batch updates the progress bar more often and loses less work when something
# fails, at the cost of more round trips to Qdrant. 32 keeps a 1200-chunk
# guideline reporting roughly every percent.
EMBED_BATCH_SIZE = _env_int("HEAL_EMBED_BATCH_SIZE", 32)


class KnowledgeNotConfigured(RuntimeError):
    """Retrieval was requested but the vector store is not configured."""


# Hosts that are only reachable from inside the deployment: the compose service
# name and the loopback addresses. Qdrant ships with no authentication, and on
# one of these an unauthenticated store is not exposed to anything. Anywhere
# else it is, so a key is mandatory there.
_PRIVATE_HOSTS = frozenset({"qdrant", "localhost", "127.0.0.1", "::1", "[::1]"})


def _hostname(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def require_knowledge_config() -> tuple[str, str]:
    """Return (url, api_key), or explain exactly what is missing.

    Called at the entry to the retrieval path rather than at import, so a
    deployment with KNOWLEDGE_ENABLED=false never touches this.

    The API key is required for any host that is not on the private list. On a
    local stack Qdrant is only reachable across the compose network, so a
    missing key is a warning rather than a refusal -- keeping local setup a
    single command without letting an open store be reached over a network.
    """
    if not QDRANT_URL:
        raise KnowledgeNotConfigured(
            "Retrieval is enabled but QDRANT_URL is not set. `make up` sets "
            "it to the vector store on the compose network; set it explicitly "
            "when running outside compose, or set KNOWLEDGE_ENABLED=false."
        )

    host = _hostname(QDRANT_URL)
    if not QDRANT_API_KEY:
        if host not in _PRIVATE_HOSTS:
            raise KnowledgeNotConfigured(
                f"QDRANT_API_KEY is required for a Qdrant at '{host}'. Qdrant "
                "has no authentication by default, so a store reachable over a "
                "network must have a key set."
            )
        _logger().warning(
            "Qdrant at %s has no API key and is unauthenticated. Acceptable on "
            "a private compose network; never in a deployment.",
            host,
        )
    return QDRANT_URL, QDRANT_API_KEY


def _logger():  # type: ignore[no-untyped-def]
    """Imported lazily: heal.logger imports this module."""
    from heal.logger import get_logger

    return get_logger(__name__)


#####
# Safety
#####

# Bumped whenever the safety instruction text changes. Written to the audit
# event on every classification so an answer can be traced to the rules that
# produced it.
SAFETY_PROMPT_VERSION = _env_str("HEAL_SAFETY_PROMPT_VERSION", "2026-08-28.1")

# Emergency escalation number shown ahead of any emergency answer.
EMERGENCY_CONTACT = _env_str("HEAL_EMERGENCY_CONTACT", "912")


#####
# Bootstrap administrator
#
# With authentication on, a brand-new database has nobody who can log in --
# and no way to create the first account, because creating accounts requires
# being logged in as an admin. This seeds exactly one account to break that
# circle.
#
# It runs ONLY when the user table is empty, so it can never overwrite a real
# account or resurrect a deleted one. Both values come from the environment:
# a password does not belong in source, and leaving them unset (the production
# default) disables seeding entirely.
#####

BOOTSTRAP_ADMIN_EMAIL = _env_str("HEAL_BOOTSTRAP_ADMIN_EMAIL")
BOOTSTRAP_ADMIN_PASSWORD = _env_str("HEAL_BOOTSTRAP_ADMIN_PASSWORD")

# Passwords that exist to get a local stack running and must never reach a
# deployment. Seeding still proceeds, loudly -- refusing would just leave a
# developer locked out with no explanation.
WEAK_BOOTSTRAP_PASSWORDS = frozenset({"password", "admin", "changeme", "heal"})
