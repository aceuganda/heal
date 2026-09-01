"""Tests for retrieval as the agent uses it.

The rule that matters clinically: for a dosage question, citing nothing is
better than citing weakly. A dose under a citation marker carries authority the
text has not earned.
"""
import pytest

from heal.knowledge.models import Chunk
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.models import SearchOutcome
from heal.knowledge.models import SourceRef
from heal.medical_guidance.agent import AgentRequest
from heal.medical_guidance.agent import MedicalGuidanceAgent
from heal.medical_guidance.understanding import Understanding
from heal.medical_guidance.routes import MedicalIntent


class FakeStore:
    """Returns a scripted outcome and records what it was asked."""

    def __init__(self, outcome: SearchOutcome | None = None) -> None:
        # `or` would discard an unavailable/below-floor outcome: both are
        # falsy. See SearchOutcome.__bool__.
        self.outcome = SearchOutcome() if outcome is None else outcome
        self.queries: list[str] = []
        self.lexical_queries: list[str | None] = []

    def search(
        self,
        query: str,
        limit: int | None = None,
        lexical_query: str | None = None,
    ) -> SearchOutcome:
        self.queries.append(query)
        # Recorded separately: the dense half searches `query`, the lexical half
        # searches this, and a test that cares about drug codes cares which.
        self.lexical_queries.append(lexical_query)
        return self.outcome


def chunk(text: str = "Give TDF/3TC/DTG once daily.", source_id: str = "src-1"):
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id="c1",
            text=text,
            source=SourceRef(
                source_id=source_id,
                title="Uganda ART Guidelines",
                version="2022",
                publisher="Ministry of Health",
            ),
        ),
        score=0.9,
    )


@pytest.fixture
def classified(monkeypatch):
    """Pin the intent so these tests exercise routing, not classification."""

    def _set(intent: MedicalIntent):
        monkeypatch.setattr(
            "heal.medical_guidance.agent.understand",
            lambda message, *a, **k: Understanding(
                intent=intent,
                query=message,
                original=message,
                classified=True,
                rewritten=True,
                model_id="fake",
                safety_version="test",
            ),
        )

    return _set


class TestUnsourcedDosageIsRefused:
    def test_a_dosage_question_with_no_source_is_refused(self, classified) -> None:
        classified(MedicalIntent.DOSAGE_OR_MEDICATION)
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=FakeStore())

        stream, response = agent.answer(AgentRequest(message="dose of DTG?"))
        text = "".join(stream)

        assert response.answered is False
        assert response.refused_unsourced is True
        assert "guess" in text.lower() or "not have an approved source" in text.lower()

    def test_the_refusal_distinguishes_outage_from_no_such_source(
        self, classified
    ) -> None:
        """A health worker in front of a patient needs to know which it is."""
        classified(MedicalIntent.DOSAGE_OR_MEDICATION)
        store = FakeStore(SearchOutcome(unavailable=True, error="ConnectionError"))
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=store)

        text = "".join(agent.answer(AgentRequest(message="dose?"))[0])

        assert "could not reach" in text.lower()

    def test_a_dosage_question_with_a_source_is_answered(self, classified) -> None:
        classified(MedicalIntent.DOSAGE_OR_MEDICATION)
        store = FakeStore(SearchOutcome(chunks=[chunk()]))
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=store)

        _, response = agent.answer(AgentRequest(message="dose of DTG?"))

        assert response.answered is True
        assert response.refused_unsourced is False
        assert [s.source_id for s in response.sources] == ["src-1"]


class TestOtherIntentsDegradeGracefully:
    def test_a_clinical_question_still_answers_without_a_source(
        self, classified
    ) -> None:
        classified(MedicalIntent.CLINICAL_QUESTION)
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=FakeStore())

        _, response = agent.answer(AgentRequest(message="what is sepsis?"))

        assert response.answered is True
        assert response.retrieved is False

    def test_smalltalk_never_touches_the_store(self, classified) -> None:
        classified(MedicalIntent.ADMIN_OR_SMALLTALK)
        store = FakeStore(SearchOutcome(chunks=[chunk()]))
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=store)

        agent.answer(AgentRequest(message="hello"))

        assert store.queries == [], "smalltalk should not query the knowledge base"

    def test_out_of_scope_declines_before_retrieving(self, classified) -> None:
        classified(MedicalIntent.OUT_OF_SCOPE)
        store = FakeStore()
        agent = MedicalGuidanceAgent(knowledge_enabled=True, store=store)

        _, response = agent.answer(AgentRequest(message="write me a poem"))

        assert response.answered is False
        assert store.queries == []


class TestKnowledgeDisabled:
    def test_retrieval_is_skipped_entirely_when_knowledge_is_off(
        self, classified
    ) -> None:
        """KNOWLEDGE_ENABLED=false must reproduce the pre-RAG behaviour."""
        classified(MedicalIntent.CLINICAL_QUESTION)
        store = FakeStore(SearchOutcome(chunks=[chunk()]))
        agent = MedicalGuidanceAgent(knowledge_enabled=False, store=store)

        _, response = agent.answer(AgentRequest(message="what is sepsis?"))

        assert store.queries == []
        assert response.retrieved is False

    def test_a_dosage_question_is_not_refused_when_knowledge_is_off(
        self, classified
    ) -> None:
        """With no library configured, refusing every dose would be useless."""
        classified(MedicalIntent.DOSAGE_OR_MEDICATION)
        agent = MedicalGuidanceAgent(knowledge_enabled=False, store=FakeStore())

        _, response = agent.answer(AgentRequest(message="dose of DTG?"))

        assert response.answered is True
        assert response.refused_unsourced is False
