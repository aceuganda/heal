"""Tests for the agent's end-to-end routing behaviour.

These are the safety tests. They assert what a health worker actually receives
for each kind of question, and that every decision is audited.
"""
import json

import pytest

from heal import config
from heal.medical_guidance import agent as agent_mod
from heal.medical_guidance import audit as audit_mod
from heal.medical_guidance import understanding as understanding_mod
from heal.medical_guidance.agent import AgentRequest
from heal.medical_guidance.agent import MedicalGuidanceAgent
from heal.medical_guidance.intent import MedicalIntent


class FakeLLM:
    """A model that classifies as told and answers with fixed tokens.

    `invoke` returns the JSON shape `understand()` asks for, rather than a bare
    label, so these tests exercise the real parser rather than a stub of it.
    """

    def __init__(self, label: str, answer: list[str]) -> None:
        self.label = label
        self.answer = answer
        self.prompts: list = []

    def invoke(self, prompt) -> str:
        return json.dumps(
            {"category": self.label, "query": "a rewritten question", "terms": []}
        )

    def stream(self, prompt):
        self.prompts.append(prompt)
        yield from self.answer


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch):
    """Install a fake model and capture audit events."""
    events: list = []
    monkeypatch.setattr(audit_mod, "emit", events.append)

    def install(label: str, answer: list[str] | None = None) -> tuple[FakeLLM, list]:
        llm = FakeLLM(label, answer if answer is not None else ["an ", "answer"])
        monkeypatch.setattr(understanding_mod, "get_classifier_llm", lambda *_: llm)
        monkeypatch.setattr(agent_mod, "get_llm", lambda model_id=None: llm)
        monkeypatch.setattr(agent_mod, "to_provider_messages", lambda m: m)
        return llm, events

    return install


def run(agent: MedicalGuidanceAgent, message: str):
    tokens, decision = agent.answer(AgentRequest(message=message))
    text = "".join(tokens)
    return text, decision


class TestNormalAnswer:
    def test_clinical_question_streams_an_answer(self, wire) -> None:
        wire("CLINICAL_QUESTION")
        text, decision = run(MedicalGuidanceAgent(), "how is malaria diagnosed")
        assert text == "an answer"
        assert decision.intent is MedicalIntent.CLINICAL_QUESTION
        assert decision.answered is True

    def test_decision_text_matches_what_was_streamed(self, wire) -> None:
        wire("CLINICAL_QUESTION")
        text, decision = run(MedicalGuidanceAgent(), "how is malaria diagnosed")
        assert decision.text == text


class TestEmergency:
    def test_escalation_copy_comes_first(self, wire) -> None:
        wire("EMERGENCY")
        text, _ = run(MedicalGuidanceAgent(), "patient unresponsive")
        assert text.startswith("**If this is a medical emergency")
        assert config.EMERGENCY_CONTACT in text

    def test_escalation_survives_a_model_that_says_nothing(self, wire) -> None:
        """The reason the preamble is emitted before generation, not after."""
        wire("EMERGENCY", answer=[])
        text, _ = run(MedicalGuidanceAgent(), "patient unresponsive")
        assert config.EMERGENCY_CONTACT in text

    def test_non_emergency_gets_no_preamble(self, wire) -> None:
        wire("CLINICAL_QUESTION")
        text, _ = run(MedicalGuidanceAgent(), "how is malaria diagnosed")
        assert "medical emergency" not in text


class TestOutOfScope:
    def test_declines_without_calling_the_model(self, wire) -> None:
        llm, _ = wire("OUT_OF_SCOPE")
        text, decision = run(MedicalGuidanceAgent(), "write me a poem")
        assert decision.answered is False
        assert "only help with clinical and health questions" in text
        assert llm.prompts == []  # generation never ran


class TestKnowledgeFlag:
    def test_phase_1_never_retrieves(self, wire) -> None:
        wire("CLINICAL_QUESTION")
        _, decision = run(MedicalGuidanceAgent(knowledge_enabled=False), "anything")
        assert decision.retrieved is False

    def test_prompt_states_there_is_no_library(self, wire) -> None:
        llm, _ = wire("CLINICAL_QUESTION")
        run(MedicalGuidanceAgent(knowledge_enabled=False), "anything")
        system_text = llm.prompts[0][0][1]
        assert "no access to the facility's approved document library" in system_text


class TestAudit:
    def test_every_answer_is_audited(self, wire) -> None:
        _, events = wire("CLINICAL_QUESTION")
        run(MedicalGuidanceAgent(), "how is malaria diagnosed")
        assert len(events) == 1
        assert events[0].intent == "CLINICAL_QUESTION"
        assert events[0].answered is True

    def test_a_refusal_is_audited_too(self, wire) -> None:
        _, events = wire("OUT_OF_SCOPE")
        run(MedicalGuidanceAgent(), "write me a poem")
        assert len(events) == 1
        assert events[0].answered is False

    def test_event_carries_no_message_text(self, wire) -> None:
        """No patient text in the audit record, ever."""
        _, events = wire("CLINICAL_QUESTION")
        run(MedicalGuidanceAgent(), "patient Namukasa has a fever of 39")
        serialised = str(vars(events[0]))
        assert "Namukasa" not in serialised
        assert "fever" not in serialised

    def test_event_records_the_versions_that_produced_it(self, wire) -> None:
        _, events = wire("CLINICAL_QUESTION")
        run(MedicalGuidanceAgent(), "how is malaria diagnosed")
        assert events[0].safety_version == config.SAFETY_PROMPT_VERSION
        assert events[0].classifier_model == config.CLASSIFIER_MODEL
