"""Retrieval: one collection, one embedding model, one writer.

Public surface deliberately small. Everything else in this package is an
implementation detail of these five things.
"""
from heal.knowledge.ingest import IngestResult
from heal.knowledge.ingest import reference_ingest
from heal.knowledge.ingest import set_approval
from heal.knowledge.ingest import supersede
from heal.knowledge.models import Chunk
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.models import SearchOutcome
from heal.knowledge.models import SourceRef
from heal.knowledge.store import ensure_collection
from heal.knowledge.store import KnowledgeStore
from heal.knowledge.store import QdrantKnowledgeStore

__all__ = [
    "Chunk",
    "IngestResult",
    "KnowledgeStore",
    "QdrantKnowledgeStore",
    "RetrievedChunk",
    "SearchOutcome",
    "SourceRef",
    "ensure_collection",
    "reference_ingest",
    "set_approval",
    "supersede",
]
