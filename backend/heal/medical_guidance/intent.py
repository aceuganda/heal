"""Medical intent classification.

Replaces two things at once:

  * `search/danswer_helper.py::query_intent` -- a TensorFlow DistilBERT that
    chose between keyword, semantic and QA search. With one collection and one
    embedding model there is nothing left for it to choose, and it is the only
    reason TensorFlow is a dependency.
  * `secondary_llm_flows/choose_search.py::check_if_need_search` -- a separate
    LLM round trip asking whether to search at all.

Both fold into one classification whose purpose is safety routing, not search
tuning. It runs on English text, after translation, so it works identically for
both languages.
"""
import re
from dataclasses import dataclass
from enum import Enum

from heal.llm import get_classifier_llm
from heal.logger import get_logger
from heal.safety import safety_version

logger = get_logger(__name__)


class MedicalIntent(str, Enum):
    """What kind of thing was asked. Drives the route table, nothing else."""

    EMERGENCY = "EMERGENCY"
    DOSAGE_OR_MEDICATION = "DOSAGE_OR_MEDICATION"
    CLINICAL_QUESTION = "CLINICAL_QUESTION"
    GENERAL_HEALTH_INFO = "GENERAL_HEALTH_INFO"
    ADMIN_OR_SMALLTALK = "ADMIN_OR_SMALLTALK"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


# When the model is unavailable or returns something unusable, fall back to the
# label that is safe to be wrong about: it still answers and still cites, it
# just does not unlock the emergency or dosage-specific handling.
FALLBACK_INTENT = MedicalIntent.CLINICAL_QUESTION


CLASSIFIER_PROMPT = """\
Classify the health worker's message into exactly one category.

EMERGENCY
  An immediate, life-threatening situation needing action now: cardiac arrest,
  anaphylaxis, severe haemorrhage, eclampsia, unresponsive or convulsing
  patient, severe respiratory distress, suspected poisoning.

DOSAGE_OR_MEDICATION
  Asks for a drug dose, route, frequency, duration, interaction,
  contraindication, or a paediatric or weight-based calculation.

CLINICAL_QUESTION
  A clinical question that is not primarily about a dose: diagnosis, symptoms,
  investigations, management steps, guideline content, referral criteria.

GENERAL_HEALTH_INFO
  Background or public-health information rather than the management of a case:
  prevention, transmission, health education, statistics.

ADMIN_OR_SMALLTALK
  Greetings, thanks, questions about this assistant, or anything about using
  the system itself.

OUT_OF_SCOPE
  Not health-related at all, or a request this assistant must refuse.

Rules:
- Answer with the category name alone. No explanation, no punctuation.
- If a message is both an emergency and a dose question, answer EMERGENCY.
- Judge the latest message. Use the history only to resolve what it refers to.

Recent conversation:
{history}

Latest message:
{message}

Category:"""


@dataclass(frozen=True)
class IntentResult:
    """A classification plus everything needed to audit it."""

    intent: MedicalIntent
    # True when the label came from the model rather than the fallback.
    classified: bool
    model_id: str
    safety_version: str
    # Set when classification failed, for the audit record. Never user-facing.
    error: str | None = None


def _format_history(history: list[str], limit: int = 4) -> str:
    """Last few turns, oldest first. Short by design: this is a routing call."""
    recent = [h.strip() for h in history if h and h.strip()][-limit:]
    return "\n".join(f"- {h}" for h in recent) if recent else "(none)"


def parse_intent(raw: str) -> MedicalIntent | None:
    """Read a label out of a model response.

    Tolerant of the usual noise -- surrounding quotes, a trailing full stop, a
    "Category:" prefix, lowercase -- but never guesses. Anything unrecognised
    returns None so the caller can fall back deliberately.
    """
    if not raw:
        return None
    text = raw.strip().upper()
    # Scan every label-shaped token and take the first that is a real label.
    # Taking only the first token would lose "Category: EMERGENCY", where the
    # leading word is the model's own scaffolding rather than the answer.
    valid = {i.value for i in MedicalIntent}
    for token in re.findall(r"[A-Z_]{4,}", text):
        if token in valid:
            return MedicalIntent(token)
    return None


def classify(message: str, history: list[str] | None = None) -> IntentResult:
    """Classify one English message.

    Never raises: a failure here must not cost the user their answer, so it
    degrades to FALLBACK_INTENT and records why.
    """
    from heal import config

    model_id = config.CLASSIFIER_MODEL
    prompt = CLASSIFIER_PROMPT.format(
        history=_format_history(history or []), message=message.strip()
    )

    try:
        raw = get_classifier_llm().invoke(prompt)
    except Exception as e:  # noqa: BLE001 -- deliberately broad, see docstring
        logger.error(f"Intent classification failed: {type(e).__name__}: {e}")
        return IntentResult(
            intent=FALLBACK_INTENT,
            classified=False,
            model_id=model_id,
            safety_version=safety_version(),
            error=f"{type(e).__name__}",
        )

    intent = parse_intent(raw)
    if intent is None:
        logger.warning("Intent classifier returned an unrecognised label")
        return IntentResult(
            intent=FALLBACK_INTENT,
            classified=False,
            model_id=model_id,
            safety_version=safety_version(),
            error="unparseable_label",
        )

    return IntentResult(
        intent=intent,
        classified=True,
        model_id=model_id,
        safety_version=safety_version(),
    )
