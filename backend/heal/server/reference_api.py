"""Plain-language glosses for a cited passage.

A clinical guideline reads like a guideline: dense, abbreviated, written for
someone who already knows the context. A health worker who opens a citation to
check a dose gets a wall of "TDF/3TC/DTG OD PO" and is no better informed than
before. This turns one cited passage into two sentences of plain English that
say what it means.

Three rules make this safe to put next to a dose:

  * The gloss NEVER replaces the passage. The UI shows the original text and
    the gloss beside it, so the reader can always see what was actually
    written and judge the paraphrase.
  * The model is given the passage and nothing else -- no chat history, no
    question. It explains the text in front of it rather than answering
    anything, which is what stops it inventing a dose the passage never gave.
  * A failure returns no gloss rather than a guess. The drawer simply shows
    the original passage, which is the state it was in before this existed.

Generated on demand and cached on the row: most citations are never opened, so
generating at answer time would pay for -- and wait for -- work nobody reads.
"""
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from heal import config
from heal.logger import get_logger
from heal_app.auth.users import current_user
from heal_app.db.engine import get_session
from heal_app.db.models import SearchDoc
from heal_app.db.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/chat/reference")

# Where the cached gloss lives on the SearchDoc row. `doc_metadata` is a JSONB
# blob the retired connector fleet used for arbitrary per-document fields, so
# reusing it avoids a migration for what is a derived, disposable value.
GLOSS_KEY = "plain_language"

# Long enough to explain a dosing rule, short enough to read in the drawer
# without scrolling.
MAX_GLOSS_WORDS = 60

_INSTRUCTION = (
    "You are helping a health worker understand one passage from a clinical "
    "guideline. Explain what the passage below says in plain English, in at "
    "most two short sentences.\n\n"
    "Rules:\n"
    "- Explain ONLY what this passage states. Add nothing from your own "
    "knowledge, and never supply a dose, drug or age the passage does not "
    "give.\n"
    "- Expand abbreviations and drug codes the first time they appear.\n"
    "- If the passage is too fragmentary to explain, reply exactly: "
    "UNCLEAR\n"
)

# The model's way of saying the passage cannot be summarised honestly.
_UNCLEAR = "UNCLEAR"


class ReferenceGloss(BaseModel):
    search_doc_id: int
    gloss: str | None = None
    cached: bool = False
    # The passage is always returned so the caller can render the drawer from
    # one request, and so it can show the original when there is no gloss.
    passage: str = ""
    title: str = ""


@router.get("/{search_doc_id}/gloss")
def get_reference_gloss(
    search_doc_id: int,
    _: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> ReferenceGloss:
    """Explain one cited passage in plain English.

    Available to any signed-in user, not just admins: this is a reading aid for
    the health worker looking at the answer.
    """
    doc = db_session.get(SearchDoc, search_doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No such reference")

    passage = (doc.match_highlights or [doc.blurb or ""])[0]
    metadata = dict(doc.doc_metadata or {})
    cached = metadata.get(GLOSS_KEY)
    if cached:
        return ReferenceGloss(
            search_doc_id=search_doc_id,
            gloss=str(cached),
            cached=True,
            passage=passage,
            title=doc.semantic_id or "",
        )

    gloss = _generate(passage)
    if gloss:
        # Written back on the row so the second reader pays nothing. A failed
        # generation is deliberately not cached -- it should be retried.
        metadata[GLOSS_KEY] = gloss
        doc.doc_metadata = metadata
        db_session.add(doc)
        db_session.commit()

    return ReferenceGloss(
        search_doc_id=search_doc_id,
        gloss=gloss,
        cached=False,
        passage=passage,
        title=doc.semantic_id or "",
    )


def _generate(passage: str) -> str | None:
    """One short completion. Returns None rather than raising or guessing."""
    if not passage.strip():
        return None

    try:
        from heal.llm import get_llm
        from heal.llm import to_provider_messages

        # The cheap model: this is a paraphrase of text already in hand, not a
        # clinical judgement, and it runs once per opened citation.
        llm = get_llm(config.CLASSIFIER_MODEL)
        prompt = [("system", _INSTRUCTION), ("user", passage)]
        answer = "".join(llm.stream(to_provider_messages(prompt))).strip()
    except Exception as exc:  # noqa: BLE001 -- the drawer degrades to the passage
        logger.error("Could not gloss a reference (%s): %s", type(exc).__name__, exc)
        return None

    if not answer or answer.upper().startswith(_UNCLEAR):
        return None

    # A model that ignores the length rule should not blow the drawer open.
    words = answer.split()
    if len(words) > MAX_GLOSS_WORDS:
        answer = " ".join(words[:MAX_GLOSS_WORDS]).rstrip(",;:") + "…"
    return answer
