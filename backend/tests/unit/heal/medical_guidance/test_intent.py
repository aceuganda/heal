"""Tests for medical intent classification.

The label set is a safety control, so the cases that matter most are the ones
where the model misbehaves: unusable output, an unknown label, an outright
failure. None of those may cost the user their answer.
"""
import pytest

from heal import config
from heal.medical_guidance import intent as intent_mod
from heal.medical_guidance.intent import classify
from heal.medical_guidance.intent import FALLBACK_INTENT
from heal.medical_guidance.intent import MedicalIntent
from heal.medical_guidance.intent import parse_intent


class FakeLLM:
    """Returns a canned response, or raises."""

    def __init__(self, response: str = "", raises: Exception | None = None) -> None:
        self.response = response
        self.raises = raises
        self.prompts: list[str] = []

    def invoke(self, prompt) -> str:
        self.prompts.append(prompt)
        if self.raises:
            raise self.raises
        return self.response


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    def install(response: str = "", raises: Exception | None = None) -> FakeLLM:
        llm = FakeLLM(response, raises)
        monkeypatch.setattr(intent_mod, "get_classifier_llm", lambda: llm)
        return llm

    return install


class TestParseIntent:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("EMERGENCY", MedicalIntent.EMERGENCY),
            ("  emergency  ", MedicalIntent.EMERGENCY),
            ("Category: DOSAGE_OR_MEDICATION", MedicalIntent.DOSAGE_OR_MEDICATION),
            ('"CLINICAL_QUESTION"', MedicalIntent.CLINICAL_QUESTION),
            ("OUT_OF_SCOPE.", MedicalIntent.OUT_OF_SCOPE),
        ],
    )
    def test_reads_a_label_through_the_usual_noise(self, raw, expected) -> None:
        assert parse_intent(raw) is expected

    @pytest.mark.parametrize("raw", ["", "   ", "banana", "42", "I think this is..."])
    def test_never_guesses(self, raw: str) -> None:
        """Unrecognised output returns None so the caller falls back on purpose."""
        assert parse_intent(raw) is None


class TestClassify:
    def test_uses_the_model_label(self, fake_llm) -> None:
        fake_llm("EMERGENCY")
        result = classify("patient is convulsing and unresponsive")
        assert result.intent is MedicalIntent.EMERGENCY
        assert result.classified is True
        assert result.error is None

    def test_unparseable_output_falls_back_without_raising(self, fake_llm) -> None:
        fake_llm("I'm not sure what you mean")
        result = classify("what is the dose of amoxicillin")
        assert result.intent is FALLBACK_INTENT
        assert result.classified is False
        assert result.error == "unparseable_label"

    def test_model_failure_falls_back_without_raising(self, fake_llm) -> None:
        fake_llm(raises=RuntimeError("upstream is down"))
        result = classify("what is the dose of amoxicillin")
        assert result.intent is FALLBACK_INTENT
        assert result.classified is False
        assert result.error == "RuntimeError"

    def test_fallback_still_answers_and_cites(self) -> None:
        """The safe-to-be-wrong label, not one that unlocks special handling."""
        assert FALLBACK_INTENT is MedicalIntent.CLINICAL_QUESTION

    def test_records_the_model_and_safety_version(self, fake_llm) -> None:
        fake_llm("CLINICAL_QUESTION")
        result = classify("how is malaria diagnosed")
        assert result.model_id == config.CLASSIFIER_MODEL
        assert result.safety_version == config.SAFETY_PROMPT_VERSION

    def test_history_is_included_and_bounded(self, fake_llm) -> None:
        llm = fake_llm("CLINICAL_QUESTION")
        classify("and in children?", [f"turn {i}" for i in range(10)])
        prompt = llm.prompts[0]
        assert "turn 9" in prompt
        assert "turn 0" not in prompt  # only the last few turns are sent

    def test_empty_history_is_stated_not_blank(self, fake_llm) -> None:
        llm = fake_llm("ADMIN_OR_SMALLTALK")
        classify("hello")
        assert "(none)" in llm.prompts[0]
