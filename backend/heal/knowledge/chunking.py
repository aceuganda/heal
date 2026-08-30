"""Splitting a document into embeddable passages.

Character windows with overlap, not a tokenizer. Two reasons: ingest needs no
model loaded to decide boundaries, and a boundary that a clinician can predict
by looking at the text is easier to argue about than one that depends on a
BPE vocabulary.

The known weakness is stated in the plan: a dosage clause whose qualifier sits
three pages earlier can be split away from it. The mitigation is the paragraph
preference below plus the diversity cap at search time, not a bigger model.
"""
import re

from heal import config

# Split on blank lines first so paragraph boundaries survive where possible.
_PARAGRAPH = re.compile(r"\n\s*\n")
# Sentence-ish boundary. Deliberately crude: it only has to beat cutting
# mid-word, and it must not need nltk (which went with the connectors).
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def normalise(text: str) -> str:
    """Collapse the whitespace noise that PDF extraction leaves behind."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split into overlapping windows, preferring paragraph then sentence ends.

    Overlap exists so a fact that lands near a boundary appears whole in at
    least one chunk.
    """
    size = chunk_size if chunk_size is not None else config.CHUNK_SIZE
    if overlap is not None:
        lap = overlap
    elif chunk_size is None:
        lap = config.CHUNK_OVERLAP
    else:
        # An explicit chunk_size with no overlap used to pick up the global
        # default, which raised whenever that default exceeded the size asked
        # for. Scale it to the window instead: surprising a caller with an
        # exception over a defaulted argument is the wrong trade.
        lap = min(config.CHUNK_OVERLAP, size // 4)
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if lap >= size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = normalise(text)
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            end = _best_break(text, start, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - lap, start + 1)
    return chunks


def _best_break(text: str, start: int, end: int) -> int:
    """Move `end` back to the nearest clean boundary, if one is close enough.

    "Close enough" is the last third of the window: searching further back
    would trade a tidy boundary for chunks half the intended size.
    """
    floor = start + (end - start) * 2 // 3

    window = text[start:end]
    para = list(_PARAGRAPH.finditer(window))
    if para and start + para[-1].start() > floor:
        return start + para[-1].start()

    sentences = list(_SENTENCE_END.finditer(window))
    if sentences and start + sentences[-1].end() > floor:
        return start + sentences[-1].end()

    space = window.rfind(" ")
    if space > 0 and start + space > floor:
        return start + space
    return end
