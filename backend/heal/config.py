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
# Phase 1 ships with retrieval OFF. The flag exists so that Phase 2 can be cut
# on Day 8 without a rollback: KNOWLEDGE_ENABLED=false must produce exactly the
# Phase 1 behaviour.
#####

KNOWLEDGE_ENABLED = _env_str("KNOWLEDGE_ENABLED", "false").lower() == "true"

# Qdrant connection. Empty in Phase 1 -- the compose files declare the service
# behind an opt-in profile, so these are only read once retrieval is on.
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
HYBRID_ALPHA = _env_float("HEAL_HYBRID_ALPHA", 0.6)

# Chunking. Characters, not tokens: the boundary only has to be stable and
# explainable, and a character window needs no tokenizer at ingest time.
CHUNK_SIZE = _env_int("HEAL_CHUNK_SIZE", 1200)
CHUNK_OVERLAP = _env_int("HEAL_CHUNK_OVERLAP", 200)


class KnowledgeNotConfigured(RuntimeError):
    """Retrieval was requested but the vector store is not configured."""


def require_knowledge_config() -> tuple[str, str]:
    """Return (url, api_key), or explain exactly which variable is missing.

    Called at the entry to the retrieval path rather than at import, so that a
    Phase 1 deployment with KNOWLEDGE_ENABLED=false never touches this.
    """
    missing = [
        name
        for name, value in (
            ("QDRANT_URL", QDRANT_URL),
            ("QDRANT_API_KEY", QDRANT_API_KEY),
        )
        if not value
    ]
    if missing:
        raise KnowledgeNotConfigured(
            "Retrieval is enabled but "
            + " and ".join(missing)
            + " is not set. Start the stack with the `knowledge` profile and set "
            "these in the environment, or set KNOWLEDGE_ENABLED=false."
        )
    return QDRANT_URL, QDRANT_API_KEY


#####
# Safety
#####

# Bumped whenever the safety instruction text changes. Written to the audit
# event on every classification so an answer can be traced to the rules that
# produced it.
SAFETY_PROMPT_VERSION = _env_str("HEAL_SAFETY_PROMPT_VERSION", "2026-08-28.1")

# Emergency escalation number shown ahead of any emergency answer.
EMERGENCY_CONTACT = _env_str("HEAL_EMERGENCY_CONTACT", "912")
