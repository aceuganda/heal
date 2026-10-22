"""References the model names when the approved library has nothing.

Most clinical questions a health worker asks are not covered by the documents a
facility has uploaded. Before this, those answers arrived with no references at
all: the model wrote a paragraph of general knowledge and the reader had
nothing to check it against, or -- worse -- the model refused to name anything,
which is not caution, it is an answer nobody can verify.

So when there are no approved passages, the model is asked to close its answer
with the standard references a health worker could check, numbered, and this
module turns that block into citations the reference drawer can open.

**These are not the same kind of thing as a library citation, and the product
must never let them look like one.**

  * A library citation points at a passage we hold, ingested from a document an
    administrator approved. The drawer shows its exact words.
  * An external reference is a NAME the model produced from its own training --
    "WHO", "Uganda Clinical Guidelines". There is no passage behind it, nothing
    was retrieved, and nothing here was checked.

Which is why an external reference is read-only in the strongest sense: it
carries no excerpt, it is never glossed (there is no text to gloss, and a
model-written "summary" of a source nobody fetched would be invention with a
citation number in front of it), and the drawer says plainly where it came
from. The reader gets a pointer to go and check, which is exactly what it is.

The two never mix. When the answer HAS approved passages, marker N means
passage N and this module does nothing at all -- see `parse()`.
"""
import re
from dataclasses import dataclass

from heal.logger import get_logger

logger = get_logger(__name__)

# The heading the model is asked to write. Matched case-insensitively and only
# at the start of a line, so a sentence containing the word "sources" mid-answer
# is not mistaken for the block.
_HEADING = re.compile(
    r"^[ \t]*(?:\*\*|__|#{1,6}[ \t]*)?(?:sources?|references?)\b"
    r"(?:[ \t]*\([^)]*\))?[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*$",
    re.IGNORECASE,
)

# One entry: "[1] WHO -- Yellow fever fact sheet". A leading bullet is tolerated
# because models add them unprompted.
_ENTRY = re.compile(r"^[ \t]*(?:[-*+][ \t]*)?\[(\d{1,2})\][ \t]*(.+?)[ \t]*$")

# Caps. A model that decides to list forty references has stopped answering the
# question, and a name longer than this is a paragraph wearing a citation.
MAX_REFS = 6
MAX_NAME_CHARS = 200


@dataclass(frozen=True)
class ExternalRef:
    """One reference the model named, with nothing behind it but the name."""

    number: int
    name: str


def parse(text: str, has_passages: bool) -> dict[int, ExternalRef]:
    """Read the trailing sources block, keyed by marker number.

    **The answer text is returned to the reader untouched.** The block stays
    where the model wrote it, so what was streamed is exactly what is stored
    and exactly what is displayed -- stripping it would leave the live message
    and the reloaded one saying different things, and would quietly edit a
    clinical answer on its way to the database. What this adds is the drawer
    entry behind each number, not a rewrite.

    `has_passages` is the whole safety argument in one argument. When the
    answer was given approved passages, marker N is passage N -- the invariant
    the reference UI, the audit trail and `select_cited()` all rest on -- and a
    block of model-named sources numbered alongside them would point a reader
    at the wrong thing. So nothing is parsed at all in that case.
    """
    if has_passages or not text:
        return {}

    lines = text.splitlines()
    heading = _last_heading(lines)
    if heading is None:
        return {}

    refs: dict[int, ExternalRef] = {}
    for line in lines[heading + 1 :]:
        if not line.strip():
            # A blank line inside the block is ordinary formatting.
            continue

        entry = _ENTRY.match(line)
        if entry is None:
            # Prose after the block: the answer has resumed.
            break

        number = int(entry.group(1))
        name = _clean(entry.group(2))
        if name and number > 0 and number not in refs and len(refs) < MAX_REFS:
            refs[number] = ExternalRef(number=number, name=name)

    return refs


def _last_heading(lines: list[str]) -> int | None:
    """Index of the final "Sources" heading line, or None.

    The last one, not the first: an answer may legitimately discuss sources
    part-way through, and the block being looked for is the one the model was
    asked to close with.
    """
    found = None
    for index, line in enumerate(lines):
        if _HEADING.match(line.rstrip("\r\n")):
            found = index
    return found


def _clean(name: str) -> str:
    """Strip the decoration models put around a source name."""
    # Repeated because the two interleave: `*WHO*.` is decoration, then
    # punctuation, then decoration again, and one pass of each leaves a stray
    # asterisk in the drawer's heading.
    for _ in range(3):
        name = name.strip().strip("*_`").strip().rstrip(".,;:")
    if len(name) > MAX_NAME_CHARS:
        logger.warning("External reference name truncated at %d chars", MAX_NAME_CHARS)
        name = name[:MAX_NAME_CHARS].rstrip() + "…"
    return name
