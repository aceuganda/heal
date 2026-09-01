"""Turning a raw token stream into the packets the UI already expects.

Borrowed in shape from Onyx's `chat/stream_processing/`. The point of the seam
is that citation extraction stops being tangled up in the token loop: the
processor takes tokens in and yields answer pieces and citations out, and can be
tested with a list of strings.

Citation extraction lives here for that reason: the model is told to write [1]
after each claim, and those markers have to be turned into something the UI can
link. Doing it over the finished answer rather than inside the token loop is
deliberate -- a marker arrives split across tokens ("[", "12", "]"), so
per-token matching finds nothing.
"""
import re
from collections.abc import Iterable
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field


@dataclass
class StreamResult:
    """Everything the caller needs after the stream has finished."""

    text: str = ""
    citations: list[int] = field(default_factory=list)


class StreamProcessor:
    """Passes tokens through, accumulating the full answer as it goes.

    The accumulated text is what gets persisted and what gets translated, so it
    must be exactly what the user saw -- hence one place accumulating it rather
    than each caller doing its own concatenation.
    """

    def __init__(self, prefix: str = "") -> None:
        # Emitted before the model's first token. Used for emergency escalation
        # copy, which must reach the user even if generation then fails.
        self._prefix = prefix
        self.result = StreamResult()

    def process(self, tokens: Iterable[str]) -> Iterator[str]:
        if self._prefix:
            self.result.text += self._prefix
            yield self._prefix

        for token in tokens:
            if not token:
                continue
            self.result.text += token
            yield token

        self.result.citations = extract_citations(self.result.text)

    @property
    def text(self) -> str:
        """The complete answer, including any prefix."""
        return self.result.text


# A citation marker as the prompt asks for it: [1], [12]. Deliberately narrow.
# `[see below]` and a markdown link's `[label](url)` must not match, and a
# bare `[` mid-sentence must not swallow the rest of the answer.
_CITATION = re.compile(r"\[(\d{1,2})\](?!\()")


def extract_citations(text: str) -> list[int]:
    """Citation numbers the answer actually used, in order of first appearance.

    Order matters: it is what the reference list is sorted by, so the first
    marker a reader meets is the first source they see.

    Run over the finished answer rather than per token, because a marker can be
    split across tokens -- "[", "12", "]" is three tokens from most providers,
    and matching per token would find nothing at all.
    """
    seen: list[int] = []
    for match in _CITATION.finditer(text):
        number = int(match.group(1))
        if number > 0 and number not in seen:
            seen.append(number)
    return seen
