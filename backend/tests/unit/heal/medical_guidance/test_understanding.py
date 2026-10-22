"""Tests for preparing a question before anything is retrieved.

Two things are being protected here.

The first is that a bad response from the model costs retrieval quality and
nothing else: every failure path has to land on the user's own text with a safe
label, because the alternative is a health worker losing their answer to a
malformed JSON response.

The second is that the rewrite never quietly changes the question. A rewrite
that adds a drug, an age or "paediatric" retrieves a different guideline, and
the answer is then confidently, citably wrong -- which is worse than no answer.
"""
import json

import pytest

from heal.medical_guidance import understanding as understanding_mod
from heal.medical_guidance.intent import MedicalIntent
from heal.medical_guidance.understanding import MAX_QUERY_CHARS
from heal.medical_guidance.understanding import MAX_TERMS
from heal.medical_guidance.understanding import parse_understanding
from heal.medical_guidance.understanding import understand
from heal.medical_guidance.understanding import Understanding


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class BrokenLLM:
    def invoke(self, prompt: str) -> str:
        raise RuntimeError("provider is down")


@pytest.fixture
def responds(monkeypatch: pytest.MonkeyPatch):
    """Install a model that returns one fixed response."""

    def install(response: str) -> FakeLLM:
        llm = FakeLLM(response)
        monkeypatch.setattr(understanding_mod, "get_classifier_llm", lambda *_: llm)
        return llm

    return install


def payload(**overrides) -> str:
    body = {
        "category": "CLINICAL_QUESTION",
        "query": "how is malaria diagnosed in adults",
        "terms": [],
    }
    body.update(overrides)
    return json.dumps(body)


class TestTheHappyPath:
    def test_the_label_routes_and_the_rewrite_is_searched(self, responds) -> None:
        responds(payload(category="DOSAGE_OR_MEDICATION", query="ART dosing at 40kg"))
        result = understand("wat z the dose")

        assert result.intent is MedicalIntent.DOSAGE_OR_MEDICATION
        assert result.query == "ART dosing at 40kg"
        assert result.rewritten is True
        assert result.classified is True

    def test_the_original_message_is_always_kept(self, responds) -> None:
        """The rewrite can be wrong, and the answering model should see what
        the health worker actually typed."""
        responds(payload(query="a tidied question"))
        assert understand("  wat z tha dose  ").original == "wat z tha dose"

    def test_clinical_identifiers_are_carried_through(self, responds) -> None:
        responds(payload(terms=["TDF/3TC/DTG", "40kg"]))
        assert understand("dose?").terms == ["TDF/3TC/DTG", "40kg"]

    def test_history_is_passed_to_the_model(self, responds) -> None:
        """Without it, "and for a child?" cannot be resolved into a question
        that stands on its own."""
        llm = responds(payload())
        understand("and for a child?", ["how do I treat malaria"])

        assert "how do I treat malaria" in llm.prompts[0]


class TestTheLexicalQuery:
    """The sparse half of the search must still see what the user typed.

    If a health worker writes TDF/3TC/DTG and the rewrite generalises it to
    "dolutegravir-based regimen", the chunk carrying the literal code has to
    keep matching. Losing an exact drug-code match to a tidier query is the one
    trade this product cannot make.
    """

    def test_it_contains_both_the_rewrite_and_the_original(self, responds) -> None:
        responds(
            payload(query="dolutegravir-based regimen dosing", terms=["TDF/3TC/DTG"])
        )
        lexical = understand("dose for TDF/3TC/DTG?").lexical_query

        assert "dolutegravir-based regimen dosing" in lexical
        assert "TDF/3TC/DTG" in lexical

    def test_it_survives_an_empty_rewrite(self, responds) -> None:
        responds(payload(query=""))
        assert "amoxicillin" in understand("amoxicillin dose").lexical_query


class TestFailureCostsQualityNotTheAnswer:
    """Every failure lands on the user's text with a label that is safe to be
    wrong about: it still answers and still cites."""

    def test_an_unreachable_model_falls_back_to_the_original(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            understanding_mod, "get_classifier_llm", lambda *_: BrokenLLM()
        )
        result = understand("how is malaria diagnosed")

        assert result.query == "how is malaria diagnosed"
        assert result.intent is MedicalIntent.CLINICAL_QUESTION
        assert result.rewritten is False
        assert result.classified is False
        assert result.error == "RuntimeError"

    def test_a_response_with_no_json_falls_back(self, responds) -> None:
        responds("I think this is a question about malaria.")
        result = understand("malaria?")

        assert result.query == "malaria?"
        assert result.rewritten is False
        assert result.error == "unparseable_response"

    def test_an_empty_response_falls_back(self, responds) -> None:
        responds("")
        assert understand("malaria?").rewritten is False

    def test_an_unknown_category_keeps_a_usable_rewrite(self, responds) -> None:
        """A bad label and a good rewrite are separate failures. Throwing the
        rewrite away because the label was unreadable helps nobody."""
        responds(payload(category="URGENT_MAYBE", query="a good rewrite"))
        result = understand("something")

        assert result.intent is MedicalIntent.CLINICAL_QUESTION
        assert result.classified is False
        assert result.query == "a good rewrite"
        assert result.rewritten is True


class TestWhatTheRewriteIsNotTrustedWith:
    def test_an_answer_shaped_rewrite_is_rejected(self, responds) -> None:
        """A rewrite far longer than a question is the model answering. Searching
        on an invented answer retrieves whatever that answer resembles."""
        responds(payload(query="x" * (MAX_QUERY_CHARS + 1)))
        result = understand("dose?")

        assert result.query == "dose?"
        assert result.rewritten is False

    def test_a_rewrite_at_the_limit_is_still_accepted(self, responds) -> None:
        long_but_allowed = "a" * MAX_QUERY_CHARS
        responds(payload(query=long_but_allowed))
        assert understand("dose?").query == long_but_allowed

    def test_a_rewrite_with_no_letters_is_rejected(self, responds) -> None:
        responds(payload(query="?? -- ..."))
        assert understand("malaria?").query == "malaria?"

    def test_a_missing_query_key_falls_back_to_the_original(self, responds) -> None:
        responds(json.dumps({"category": "CLINICAL_QUESTION"}))
        result = understand("malaria?")

        assert result.query == "malaria?"
        assert result.rewritten is False
        # The label was still readable, so this is not a classification failure.
        assert result.classified is True


class TestReadingTheResponse:
    def test_a_code_fence_does_not_defeat_it(self) -> None:
        """Rejecting a good rewrite over a markdown fence would send every
        message down the fallback path."""
        parsed = parse_understanding(f"```json\n{payload()}\n```")

        assert parsed is not None
        assert parsed[0] is MedicalIntent.CLINICAL_QUESTION

    def test_a_sentence_of_preamble_does_not_defeat_it(self) -> None:
        parsed = parse_understanding(f"Here is the JSON you asked for:\n{payload()}")

        assert parsed is not None
        assert parsed[1] == "how is malaria diagnosed in adults"

    def test_a_trailing_second_object_is_ignored(self) -> None:
        """Taking everything between the first and last brace would turn two
        valid objects into one unreadable blob."""
        parsed = parse_understanding(f'{payload()}\n\nExample: {{"category": "X"}}')

        assert parsed is not None
        assert parsed[0] is MedicalIntent.CLINICAL_QUESTION

    def test_a_brace_that_opens_nothing_is_survived(self) -> None:
        assert parse_understanding("{ this is not json at all") is None

    def test_nested_braces_are_balanced_correctly(self) -> None:
        raw = json.dumps(
            {"category": "EMERGENCY", "query": "q", "terms": [], "extra": {"a": 1}}
        )
        parsed = parse_understanding(raw)

        assert parsed is not None
        assert parsed[0] is MedicalIntent.EMERGENCY

    def test_a_brace_inside_a_string_does_not_end_the_object(self) -> None:
        parsed = parse_understanding(payload(query="what about } this"))

        assert parsed is not None
        assert parsed[1] == "what about } this"


class TestTerms:
    def test_duplicates_are_dropped_and_order_is_kept(self) -> None:
        parsed = parse_understanding(payload(terms=["500mg", "BD", "500mg"]))

        assert parsed is not None
        assert parsed[2] == ["500mg", "BD"]

    def test_a_sentence_is_not_an_identifier(self) -> None:
        """A "term" the length of a sentence is the model quoting the passage."""
        parsed = parse_understanding(payload(terms=["x" * 41, "40kg"]))

        assert parsed is not None
        assert parsed[2] == ["40kg"]

    def test_the_list_is_bounded(self) -> None:
        parsed = parse_understanding(payload(terms=[f"t{i}" for i in range(50)]))

        assert parsed is not None
        assert len(parsed[2]) == MAX_TERMS

    def test_a_non_list_is_ignored_rather_than_raising(self) -> None:
        parsed = parse_understanding(payload(terms="TDF/3TC/DTG"))

        assert parsed is not None
        assert parsed[2] == []

    def test_numbers_are_accepted(self) -> None:
        """Models return `40` for a weight as often as `"40kg"`."""
        parsed = parse_understanding(payload(terms=[40, "kg"]))

        assert parsed is not None
        assert parsed[2] == ["40", "kg"]


class TestTheAuditRecord:
    def test_a_successful_rewrite_is_recorded_as_one(self, responds) -> None:
        responds(payload())
        result = understand("malaria?")

        assert result.rewritten is True
        assert result.error is None
        assert result.model_id
        assert result.safety_version

    def test_the_fallback_path_is_distinguishable(self, responds) -> None:
        """ "Searched the raw text" and "searched a rewrite" are different things
        to debug when a retrieval goes wrong."""
        responds("not json")
        assert understand("malaria?").rewritten is False


class TestUnderstandingIsAValue:
    def test_it_is_frozen(self) -> None:
        result = Understanding(
            intent=MedicalIntent.CLINICAL_QUESTION, query="q", original="o"
        )
        with pytest.raises(Exception):
            result.query = "changed"  # type: ignore[misc]
