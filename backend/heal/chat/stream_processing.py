"""Turning a raw token stream into the packets the UI already expects.

Borrowed in shape from Onyx's `chat/stream_processing/`. The point of the seam
is that citation extraction stops being tangled up in the token loop: the
processor takes tokens in and yields answer pieces and citations out, and can be
tested with a list of strings.

Phase 1 has no retrieval, so there are no citations to extract. The class still
exists, and still runs, so that Phase 2 adds citation handling in one place
rather than reopening the chat loop.
"""
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

    @property
    def text(self) -> str:
        """The complete answer, including any prefix."""
        return self.result.text
