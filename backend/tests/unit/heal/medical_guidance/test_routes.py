"""Tests for the fixed route table.

The table is the safety control: the model picks a label, the table decides what
happens. These tests assert the decisions, not the wording.
"""
import pytest

from heal import config
from heal.medical_guidance.intent import MedicalIntent
from heal.medical_guidance.routes import emergency_preamble
from heal.medical_guidance.routes import route_for
from heal.medical_guidance.routes import ROUTES


class TestCoverage:
    def test_every_intent_has_a_route(self) -> None:
        """No default: an unrouted intent must be a loud failure, not a guess."""
        assert set(ROUTES) == set(MedicalIntent)

    @pytest.mark.parametrize("intent", list(MedicalIntent))
    def test_route_lookup_never_raises(self, intent: MedicalIntent) -> None:
        assert route_for(intent) is not None


class TestDecisions:
    def test_dosage_requires_a_source(self) -> None:
        """Citing a weak match on a dose is worse than refusing."""
        assert route_for(MedicalIntent.DOSAGE_OR_MEDICATION).require_source is True

    def test_only_dosage_requires_a_source(self) -> None:
        requiring = {i for i in MedicalIntent if route_for(i).require_source}
        assert requiring == {MedicalIntent.DOSAGE_OR_MEDICATION}

    def test_out_of_scope_declines(self) -> None:
        route = route_for(MedicalIntent.OUT_OF_SCOPE)
        assert route.answer is False
        assert route.retrieve is False
        assert route.decline_message

    def test_out_of_scope_is_the_only_refusal(self) -> None:
        refusing = {i for i in MedicalIntent if not route_for(i).answer}
        assert refusing == {MedicalIntent.OUT_OF_SCOPE}

    def test_smalltalk_does_not_retrieve_or_cite(self) -> None:
        route = route_for(MedicalIntent.ADMIN_OR_SMALLTALK)
        assert route.retrieve is False
        assert route.answer is True

    def test_clinical_intents_retrieve(self) -> None:
        for intent in (
            MedicalIntent.EMERGENCY,
            MedicalIntent.DOSAGE_OR_MEDICATION,
            MedicalIntent.CLINICAL_QUESTION,
            MedicalIntent.GENERAL_HEALTH_INFO,
        ):
            assert route_for(intent).retrieve is True


class TestEmergencyPreamble:
    def test_carries_the_configured_contact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "EMERGENCY_CONTACT", "0800-TEST")
        assert "0800-TEST" in emergency_preamble()

    def test_is_read_at_call_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Changing the contact must not need a redeploy of the route table."""
        monkeypatch.setattr(config, "EMERGENCY_CONTACT", "111")
        first = emergency_preamble()
        monkeypatch.setattr(config, "EMERGENCY_CONTACT", "222")
        assert first != emergency_preamble()
