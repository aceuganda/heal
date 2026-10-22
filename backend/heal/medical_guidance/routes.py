"""The route table.

The model classifies; this table decides what happens next. That split is the
whole point of D3: no tool loop, no planner, no model-chosen action. Changing a
route is a code change with review, not a prompt tweak.
"""
from dataclasses import dataclass

from heal import config
from heal.medical_guidance.intent import MedicalIntent


@dataclass(frozen=True)
class Route:
    """What the agent does for one intent."""

    # Attempt retrieval for this intent (Phase 2; ignored while knowledge is off).
    retrieve: bool
    # Refuse rather than answer unsourced. Only meaningful with knowledge on.
    require_source: bool
    # Answer at all, or decline and redirect.
    answer: bool
    # Prepended to the answer before the model is called.
    preamble: str = ""
    # Sent instead of an answer when `answer` is False.
    decline_message: str = ""
    # Extra instruction appended to the system prompt for this intent.
    instruction: str = ""


def _emergency_preamble() -> str:
    return (
        f"**If this is a medical emergency, get help now — call "
        f"{config.EMERGENCY_CONTACT} or your facility's emergency team, and "
        f"start resuscitation or first-line management immediately.**\n\n"
    )


ROUTES: dict[MedicalIntent, Route] = {
    # Escalation copy goes out FIRST, before the model is even called, so the
    # user sees it even if generation is slow or fails.
    MedicalIntent.EMERGENCY: Route(
        retrieve=True,
        require_source=False,
        answer=True,
        preamble="",  # built at call time; see emergency_preamble()
        instruction=(
            "This is an emergency. Lead with the immediate actions in order, "
            "as a short numbered list. Put the single most time-critical step "
            "first. Keep background to a minimum."
        ),
    ),
    # The one intent where citing nothing is better than citing weakly.
    MedicalIntent.DOSAGE_OR_MEDICATION: Route(
        retrieve=True,
        require_source=True,
        answer=True,
        instruction=(
            "State the dose, route, frequency and duration explicitly, and name "
            "the population it applies to (adult, paediatric, weight-based). If "
            "the dose depends on a fact you were not given, ask for that fact "
            "instead of assuming it. If you are not confident, say so and name "
            "the guideline to check."
        ),
    ),
    MedicalIntent.CLINICAL_QUESTION: Route(
        retrieve=True,
        require_source=False,
        answer=True,
    ),
    MedicalIntent.GENERAL_HEALTH_INFO: Route(
        retrieve=True,
        require_source=False,
        answer=True,
    ),
    MedicalIntent.ADMIN_OR_SMALLTALK: Route(
        retrieve=False,
        require_source=False,
        answer=True,
        instruction=(
            "This is not a clinical question. Answer briefly and plainly, and "
            "do not add clinical caveats."
        ),
    ),
    MedicalIntent.OUT_OF_SCOPE: Route(
        retrieve=False,
        require_source=False,
        answer=False,
        decline_message=(
            "I can only help with clinical and health questions. Ask me about "
            "a condition, a medicine, a guideline, or how to manage a case."
        ),
    ),
}


def route_for(intent: MedicalIntent) -> Route:
    """The route for an intent. Every intent has one; there is no default."""
    return ROUTES[intent]


def emergency_preamble() -> str:
    """Escalation text, read at call time so the contact number stays config."""
    return _emergency_preamble()
