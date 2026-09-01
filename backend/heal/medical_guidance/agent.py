"""MedicalGuidanceAgent -- the only agent (D3).

A straight line, not a loop. It classifies, looks the route up in a fixed table,
builds a prompt, streams an answer, and records what it did. The model never
chooses an action: there is no tool selection, no planner, no handoff, and no
background task.

Contrast with what it replaces: `stream_chat_message` made three separate
secondary-LLM round trips (`check_if_need_search`, query rephrase, chunk filter)
before it ever answered. This makes one classification call and then answers.
"""
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from heal import config
from heal.chat.prompt_builder import PromptBuilder
from heal.chat.stream_processing import StreamProcessor
from heal.knowledge.models import SearchOutcome
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.models import SourceRef
from heal.llm import get_llm
from heal.llm import to_provider_messages
from heal.logger import get_logger
from heal.medical_guidance import audit
from heal.medical_guidance.routes import emergency_preamble
from heal.medical_guidance.routes import MedicalIntent
from heal.medical_guidance.routes import route_for
from heal.medical_guidance.understanding import understand
from heal.medical_guidance.understanding import Understanding
from heal.safety import safety_version

if TYPE_CHECKING:
    from heal.knowledge.store import KnowledgeStore

logger = get_logger(__name__)


@dataclass
class AgentRequest:
    """One turn's input. English only -- translation happens upstream."""

    message: str
    # Prior turns as (is_user, text), oldest first.
    history: list[tuple[bool, str]] = field(default_factory=list)
    language: str = "english"
    chat_session_id: int | None = None
    message_id: int | None = None
    model_id: str | None = None


@dataclass
class AgentResponse:
    """What the agent decided, available after the stream is consumed."""

    intent: MedicalIntent
    answered: bool
    retrieved: bool
    text: str = ""
    # Sources actually placed in the prompt, in citation order. The caller
    # renders these; the model is never trusted to name a source itself.
    sources: list[SourceRef] = field(default_factory=list)
    # The same passages, with their text and scores. Index i is citation i+1,
    # which is the mapping the whole reference UI depends on: the caller needs
    # the passage itself to show what a citation marker actually points at.
    chunks: list["RetrievedChunk"] = field(default_factory=list)
    # The question as retrieval saw it, after rewriting. Recorded so a bad
    # retrieval can be traced to the query that produced it rather than to the
    # message the user typed, which may not be what was searched.
    search_query: str = ""
    # True when the answer was refused for lack of an approved source.
    refused_unsourced: bool = False


class MedicalGuidanceAgent:
    """Answers one clinical message, safely and auditably."""

    def __init__(
        self,
        knowledge_enabled: bool | None = None,
        store: "KnowledgeStore | None" = None,
    ) -> None:
        self.knowledge_enabled = (
            config.KNOWLEDGE_ENABLED if knowledge_enabled is None else knowledge_enabled
        )
        # Injected so the agent can be tested without Qdrant, and so swapping
        # the store is a constructor argument rather than an edit here.
        self._store = store

    def answer(self, request: AgentRequest) -> tuple[Iterator[str], AgentResponse]:
        """Classify, route, and return a token stream plus the decision record.

        The stream is lazy: nothing is sent to the model until it is consumed.
        The AgentResponse is filled in as the stream runs, so read `text` only
        after the stream is exhausted.
        """
        # One call produces both the safety label and the query retrieval will
        # search on. See heal/medical_guidance/understanding.py for why these
        # are not two separate stages.
        result = understand(request.message, [t for _, t in request.history])
        route = route_for(result.intent)

        response = AgentResponse(
            intent=result.intent,
            answered=route.answer,
            retrieved=False,
            search_query=result.query,
        )

        if not route.answer:
            self._audit(request, result, response)
            return iter([route.decline_message]), _fill(response, route.decline_message)

        # Retrieval is a direct call, never a tool the model may choose. The
        # route table decided this deterministically, before the model ran.
        outcome = SearchOutcome()
        if route.retrieve and self.knowledge_enabled:
            outcome = self._retrieve(result)
            response.retrieved = bool(outcome)
            response.sources = outcome.sources
            response.chunks = outcome.chunks

        # The one place citing nothing beats citing weakly. A dose given under
        # a citation marker carries authority the text has not earned, so with
        # no approved source the agent refuses instead of answering from
        # memory. Everything else degrades to an unsourced general answer.
        #
        # Gated on knowledge_enabled: a deployment with no library configured
        # must behave exactly as it did before retrieval existed. Without this
        # check, turning the library off would refuse EVERY dosage question --
        # the most common thing a health worker asks.
        if route.require_source and self.knowledge_enabled and not outcome:
            message = _no_source_message(outcome)
            response.answered = False
            response.refused_unsourced = True
            self._audit(request, result, response)
            return iter([message]), _fill(response, message)

        builder = PromptBuilder(
            knowledge_enabled=self.knowledge_enabled,
            route_instruction=route.instruction,
            history=request.history,
            context=[c.text for c in outcome.chunks],
            context_labels=[c.source.label() for c in outcome.chunks],
        )
        prompt = builder.build(request.message)

        # Emergency escalation goes out before the model is called, so it
        # reaches the user even if generation is slow or fails outright.
        prefix = (
            emergency_preamble() if result.intent is MedicalIntent.EMERGENCY else ""
        )
        processor = StreamProcessor(prefix=prefix)

        def stream() -> Iterator[str]:
            try:
                llm = get_llm(request.model_id)
                yield from processor.process(llm.stream(to_provider_messages(prompt)))
            finally:
                response.text = processor.text
                self._audit(request, result, response)

        return stream(), response

    @property
    def store(self) -> "KnowledgeStore":
        """The knowledge store, built on first use so Phase 1 never loads it."""
        if self._store is None:
            from heal.knowledge.store import QdrantKnowledgeStore

            self._store = QdrantKnowledgeStore()
        return self._store

    def _retrieve(self, understanding: Understanding) -> SearchOutcome:
        """Search approved sources. Never raises into the chat path.

        The rewritten question is embedded; the lexical half also sees the
        user's own wording, so an exact drug code they typed still matches even
        when the rewrite phrased it more generally.
        """
        outcome = self.store.search(
            understanding.query,
            limit=config.CONTEXT_TOP_K,
            lexical_query=understanding.lexical_query,
        )
        if outcome.unavailable:
            logger.error(
                "Retrieval unavailable (%s); answering unsourced", outcome.error
            )
        elif outcome.below_floor:
            logger.info(
                "Retrieval returned nothing above the score floor (best %.3f)",
                outcome.best_score_before_floor,
            )
        return outcome

    def _audit(
        self,
        request: AgentRequest,
        result: Understanding,
        response: AgentResponse,
    ) -> None:
        audit.emit(
            audit.RoutingEvent(
                chat_session_id=request.chat_session_id,
                message_id=request.message_id,
                intent=result.intent.value,
                classified=result.classified,
                retrieved=response.retrieved,
                answered=response.answered,
                language=request.language,
                sources=[s.source_id for s in response.sources],
                refused_unsourced=response.refused_unsourced,
                rewritten=result.rewritten,
                classifier_model=result.model_id,
                chat_model=request.model_id or config.CHAT_MODEL,
                safety_version=safety_version(),
                knowledge_enabled=self.knowledge_enabled,
                error=result.error,
            )
        )


def _no_source_message(outcome: SearchOutcome) -> str:
    """What the user sees when a dosage question has no approved source.

    Names the reason, because "temporarily unavailable" and "nothing approved
    covers this" call for different actions from a health worker standing in
    front of a patient.
    """
    if outcome.unavailable:
        return (
            "I could not reach the approved reference library just now, so I "
            "will not give a dose from memory. Please check the national "
            "guideline or your facility protocol, and try again shortly."
        )
    return (
        "I do not have an approved source covering this dose, so I will not "
        "guess at one. Please check the current national treatment guideline "
        "or your facility protocol. I can help with the surrounding clinical "
        "question if that is useful."
    )


def _fill(response: AgentResponse, text: str) -> AgentResponse:
    response.text = text
    return response
