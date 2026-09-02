"""Audit events for routing decisions.

Every classification is recorded so that an answer can be explained after the
fact: which intent was chosen, which route ran, which models produced it.

**No patient text, no message content, no user-identifying free text ever goes
into an event.** Only ids, labels and versions. That rule is what makes these
events safe to ship to ordinary log storage.

Phase 1 emits structured log lines rather than database rows. Persisting them is
a table, and the Alembic baseline is being rewritten this week -- adding a table
mid-rebaseline would put it in the wrong place in the history. `emit()` is the
seam: when the table exists, it writes there instead and no call site changes.
"""
import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone

from heal.logger import get_logger

logger = get_logger("heal.audit")


@dataclass
class RoutingEvent:
    """One routing decision, with nothing in it that could identify a patient."""

    chat_session_id: int | None
    message_id: int | None
    intent: str
    # False when the label came from the fallback rather than the model.
    classified: bool
    retrieved: bool
    answered: bool
    language: str
    classifier_model: str
    chat_model: str
    safety_version: str
    knowledge_enabled: bool
    # Source ids cited in the answer, in citation order. Ids and versions only
    # -- never source text, and never the question that retrieved them.
    sources: list[str] = field(default_factory=list)
    # True when a dosage question was refused for lack of an approved source.
    # Counting these is how you tell a working score floor from one set too high.
    refused_unsourced: bool = False
    # True when the question was successfully rewritten before retrieval. False
    # means the search ran on the user's raw text, which is the fallback path
    # and a different thing to debug.
    rewritten: bool = False
    # True when `chat_model` is not the model that was asked for, because the
    # internal endpoint could not be reached. Counting these is how you tell a
    # flaky internal box from a healthy one.
    model_failed_over: bool = False
    error: str | None = None
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def emit(event: RoutingEvent) -> None:
    """Record a routing event.

    Never raises: an audit failure must not cost a health worker their answer.
    """
    try:
        logger.info(f"routing_event {json.dumps(asdict(event), sort_keys=True)}")
    except Exception as e:  # noqa: BLE001 -- auditing must never break chat
        logger.error(f"Failed to emit routing event: {type(e).__name__}: {e}")
