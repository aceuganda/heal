"""Getting the knowledge store ready before an admin needs it.

Two things used to happen on the first upload instead of at boot: creating the
Qdrant collection, and loading the sentence-transformers model. Together they
made the first "Upload and index" click sit for a minute or fail outright, in a
UI with nothing to say about why.

Both are done here, off the boot path, so the API answers immediately and the
first upload is as fast as the second. Neither is fatal: Qdrant may still be
starting, and retrieval degrades to an unavailable store rather than a dead API.
"""
import threading

from heal import config
from heal.logger import get_logger

logger = get_logger(__name__)


def prepare_knowledge_store() -> None:
    """Create the collection and load the embedding model. Never raises."""
    from heal.knowledge.embedder import get_embedder
    from heal.knowledge.store import ensure_collection

    try:
        ensure_collection()
    except Exception as exc:  # noqa: BLE001 -- retried on the first ingest
        logger.warning(
            "Could not prepare the Qdrant collection at startup (%s: %s). "
            "It will be created on the first upload.",
            type(exc).__name__,
            exc,
        )

    try:
        # Embedding one token is what actually pulls the weights into memory.
        get_embedder().embed_query("warm up")
        logger.info("Embedding model %s ready", config.EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001 -- the first upload retries
        logger.warning(
            "Could not load the embedding model at startup (%s: %s). "
            "The first upload will load it instead.",
            type(exc).__name__,
            exc,
        )


def prepare_knowledge_store_in_background() -> None:
    """Run the preparation without holding up the server's first request."""
    if not config.KNOWLEDGE_ENABLED:
        logger.info("Knowledge retrieval is off; skipping store preparation")
        return
    threading.Thread(
        target=prepare_knowledge_store,
        name="knowledge-warmup",
        daemon=True,
    ).start()
