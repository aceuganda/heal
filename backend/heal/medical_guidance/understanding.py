"""Understanding the question before anything is retrieved.

A health worker types on a phone, in a hurry, often in their second language.
What arrives is rarely a well-formed search query: "wat z the dose of TDF/3TC/DTG
for a 14yr old, she weighs 40kg". Embedding that verbatim asks the vector store
to match phone-keyboard spelling against the prose of a national guideline.

This module turns one message into everything the rest of the turn needs:

  * the LABEL that drives the safety route table, and
  * the QUERY that retrieval actually searches on -- the same question, spelled
    correctly, with references resolved and stated the way a guideline would
    state it.

Both come from ONE call. The obvious design is a grammar-fixing stage followed
by a classifier, and it is worse: the two tasks need the same input, reading it
twice doubles the latency a health worker waits through before anything appears,
and it creates a class of bug where the two stages disagree about what was
asked.

The model is reached through `heal.llm`, so which model this is remains a
configuration question -- including a self-hosted endpoint.

Nothing here answers the question. It produces a query and a label; content
comes later, from the model that has the approved passages in front of it.
"""
import json
import re
from dataclasses import dataclass
from dataclasses import field

from heal.llm import get_classifier_llm
from heal.logger import get_logger
from heal.medical_guidance.intent import FALLBACK_INTENT
from heal.medical_guidance.intent import MedicalIntent
from heal.medical_guidance.intent import parse_intent
from heal.safety import safety_version

logger = get_logger(__name__)

# A rewrite longer than this is the model answering rather than rephrasing.
# Truncating would leave a half-sentence query, so an over-long rewrite is
# rejected outright and the original text is used instead.
MAX_QUERY_CHARS = 300

# Clinical identifiers worth carrying through verbatim. More than a handful
# means the model is listing the passage rather than the question.
MAX_TERMS = 8


UNDERSTANDING_PROMPT = """\
You prepare a health worker's message for a clinical reference search. You do
NOT answer it.

Return a JSON object with exactly these keys:

"category": one of
  EMERGENCY
    An immediate, life-threatening situation needing action now: cardiac
    arrest, anaphylaxis, severe haemorrhage, eclampsia, unresponsive or
    convulsing patient, severe respiratory distress, suspected poisoning.
  DOSAGE_OR_MEDICATION
    Asks for a drug dose, route, frequency, duration, interaction,
    contraindication, or a paediatric or weight-based calculation.
  CLINICAL_QUESTION
    A clinical question that is not primarily about a dose: diagnosis,
    symptoms, investigations, management steps, guideline content, referral.
  GENERAL_HEALTH_INFO
    Background or public-health information rather than management of a case.
  ADMIN_OR_SMALLTALK
    Greetings, thanks, questions about this assistant or about using it.
  OUT_OF_SCOPE
    Not health-related at all, or a request that must be refused.

"query": the message rewritten as ONE specific clinical question, for searching
  a medical guideline. You MAY: fix spelling and grammar; resolve what the
  message refers to using the history, so the question stands on its own;
  expand an abbreviation that is ambiguous on its own; use the vocabulary a
  clinical guideline would use.

"terms": a list of the exact clinical identifiers that appear in the message and
  must match literally -- drug codes, regimen names, doses, units, ages,
  weights. Copy them EXACTLY as written. Empty list if there are none.

Hard rules:
- NEVER answer the question. "query" is a question, never a fact or a dose.
- NEVER add a drug, dose, age, weight, sex or condition that is not in the
  message or the history. Inventing "paediatric" for a question about an adult
  retrieves the wrong guideline, and the answer is then confidently wrong.
- If the message is already a clear question, return it close to unchanged.
- If the message is a greeting or not health-related, put the message itself in
  "query" and leave "terms" empty.
- If a message is both an emergency and a dose question, the category is
  EMERGENCY.
- Judge the latest message. Use the history only to resolve what it refers to.
- Output the JSON object alone. No commentary, no code fence.

Recent conversation:
{history}

Latest message:
{message}

JSON:"""


@dataclass(frozen=True)
class Understanding:
    """One message, prepared for routing and for retrieval."""

    # Drives the route table. Nothing else.
    intent: MedicalIntent
    # What retrieval embeds: the cleaned, specific question.
    query: str
    # The user's own words, unchanged. Kept because the rewrite can be wrong,
    # and because the answering model should see what was actually typed.
    original: str
    # Clinical identifiers to preserve for lexical matching.
    terms: list[str] = field(default_factory=list)

    # --- audit -----------------------------------------------------------
    classified: bool = False
    # False when the query is just the original text -- either the call failed
    # or the rewrite was rejected.
    rewritten: bool = False
    model_id: str = ""
    safety_version: str = ""
    error: str | None = None

    @property
    def lexical_query(self) -> str:
        """Text for the sparse half of the search: rewrite plus original.

        The dense half embeds the rewrite, because that is the version phrased
        like the guideline it has to match. The lexical half must see the
        original too: if the health worker typed `TDF/3TC/DTG` and the rewrite
        generalised it to "dolutegravir-based regimen", the exact code is still
        in the vector and the chunk carrying it still matches. Losing an exact
        drug-code match to a tidier query is the one trade this product cannot
        make.
        """
        parts = [self.query, self.original, " ".join(self.terms)]
        return " ".join(part for part in parts if part.strip())


def understand(message: str, history: list[str] | None = None) -> Understanding:
    """Classify and rewrite one English message.

    Never raises. On any failure the label falls back to CLINICAL_QUESTION and
    the query falls back to the user's own text -- which is exactly how the
    system behaved before this step existed, so a bad day for the model costs
    retrieval quality rather than the answer.
    """
    from heal import config

    original = message.strip()
    model_id = config.CLASSIFIER_MODEL
    prompt = UNDERSTANDING_PROMPT.format(
        history=_format_history(history or []), message=original
    )

    try:
        raw = get_classifier_llm().invoke(prompt)
    except Exception as e:  # noqa: BLE001 -- deliberately broad, see docstring
        logger.error(f"Query understanding failed: {type(e).__name__}: {e}")
        return _fallback(original, model_id, f"{type(e).__name__}")

    parsed = parse_understanding(raw)
    if parsed is None:
        logger.warning("Query understanding returned no usable JSON")
        return _fallback(original, model_id, "unparseable_response")

    intent, query, terms = parsed
    if intent is None:
        # A usable rewrite with an unusable label is still worth keeping: the
        # safe label answers and cites, it just does not unlock the emergency
        # or dosage-specific handling.
        logger.warning("Query understanding returned an unrecognised category")

    accepted = _accept_query(query, original)
    return Understanding(
        intent=intent or FALLBACK_INTENT,
        query=accepted or original,
        original=original,
        terms=terms,
        classified=intent is not None,
        rewritten=accepted is not None,
        model_id=model_id,
        safety_version=safety_version(),
        error=None if intent is not None else "unparseable_label",
    )


def parse_understanding(
    raw: str,
) -> tuple[MedicalIntent | None, str, list[str]] | None:
    """Read (category, query, terms) out of a model response.

    Tolerant of the usual noise -- a ```json fence, a sentence of preamble --
    because rejecting a good rewrite over a code fence would send every message
    down the fallback path. Returns None only when there is no JSON object at
    all to read.
    """
    if not raw or not raw.strip():
        return None

    payload = _first_json_object(raw)
    if payload is None:
        return None

    intent = parse_intent(str(payload.get("category", "")))
    query = str(payload.get("query", "") or "").strip()
    terms = _clean_terms(payload.get("terms"))
    return intent, query, terms


def _first_json_object(raw: str) -> dict | None:
    """The first well-formed JSON object in the text, or None.

    Scans for a balanced `{...}` rather than taking everything between the
    first and last brace: a model that adds a trailing example would otherwise
    produce one unparseable blob out of two valid objects.
    """
    start = raw.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(raw[start : index + 1])
                    except ValueError:
                        break
                    if isinstance(candidate, dict):
                        return candidate
                    break
        start = raw.find("{", start + 1)
    return None


def _clean_terms(value: object) -> list[str]:
    """Identifiers only: short, non-empty, de-duplicated, order preserved."""
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        if not isinstance(item, (str, int, float)):
            continue
        term = str(item).strip()
        # A "term" the length of a sentence is the model quoting the passage.
        if not term or len(term) > 40 or term in seen:
            continue
        seen.append(term)
        if len(seen) >= MAX_TERMS:
            break
    return seen


def _accept_query(query: str, original: str) -> str | None:
    """The rewrite, or None if it should not be trusted.

    Three rejections, each a real failure mode rather than a hypothetical:

      * empty -- nothing to search with;
      * far longer than the message -- the model answered instead of rephrasing,
        and searching on an invented answer retrieves whatever that answer
        happens to resemble;
      * no letters -- punctuation or an empty JSON string dressed up.
    """
    query = query.strip()
    if not query:
        return None
    if len(query) > MAX_QUERY_CHARS:
        logger.warning(
            "Rejecting a %d-character rewrite of a %d-character message",
            len(query),
            len(original),
        )
        return None
    if not re.search(r"[A-Za-z]", query):
        return None
    return query


def _fallback(original: str, model_id: str, error: str) -> Understanding:
    """Route safely and search on exactly what the user typed."""
    return Understanding(
        intent=FALLBACK_INTENT,
        query=original,
        original=original,
        terms=[],
        classified=False,
        rewritten=False,
        model_id=model_id,
        safety_version=safety_version(),
        error=error,
    )


def _format_history(history: list[str], limit: int = 4) -> str:
    """Last few turns, oldest first. Short by design: this is a routing call."""
    recent = [h.strip() for h in history if h and h.strip()][-limit:]
    return "\n".join(f"- {h}" for h in recent) if recent else "(none)"
