"""Tests for document splitting."""
from heal.knowledge.chunking import normalise
from heal.knowledge.chunking import split_text


class TestNormalise:
    def test_collapses_the_whitespace_pdf_extraction_leaves(self) -> None:
        assert normalise("a  \t b\r\n\r\n\r\n\r\nc") == "a b\n\nc"


class TestSplitText:
    def test_short_text_is_one_chunk(self) -> None:
        assert split_text("A short note.", chunk_size=100) == ["A short note."]

    def test_empty_text_produces_no_chunks(self) -> None:
        assert split_text("   \n\n  ") == []

    def test_long_text_is_split(self) -> None:
        chunks = split_text("word " * 500, chunk_size=200, overlap=20)
        assert len(chunks) > 1
        assert all(len(c) <= 200 for c in chunks)

    def test_chunks_overlap_so_boundary_facts_survive_whole(self) -> None:
        """A dose split across a boundary must appear intact in one chunk."""
        text = ("filler. " * 40) + "Give 500mg twice daily. " + ("filler. " * 40)
        chunks = split_text(text, chunk_size=200, overlap=80)
        assert any("500mg twice daily" in c for c in chunks)

    def test_prefers_paragraph_boundaries(self) -> None:
        """A paragraph end is used when it falls in the last third of the window.

        Earlier than that it is ignored on purpose -- breaking at the first
        blank line would emit a 20-character chunk and waste the window.
        """
        body = "x" * 100
        text = body + "\n\nSecond paragraph starts here and continues."
        chunks = split_text(text, chunk_size=140, overlap=20)
        assert chunks[0] == body

    def test_ignores_a_paragraph_break_too_early_in_the_window(self) -> None:
        text = "Short intro.\n\n" + ("x" * 150)
        chunks = split_text(text, chunk_size=180, overlap=20)
        assert len(chunks[0]) > len("Short intro.")

    def test_does_not_cut_mid_word(self) -> None:
        chunks = split_text(" ".join(["alpha"] * 200), chunk_size=120, overlap=20)
        for chunk in chunks:
            assert not chunk.endswith("alph")

    def test_rejects_overlap_at_or_above_chunk_size(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            split_text("text", chunk_size=100, overlap=100)

    def test_always_terminates_on_pathological_input(self) -> None:
        """A window with no break point must still advance."""
        chunks = split_text("x" * 1000, chunk_size=100, overlap=90)
        assert len(chunks) > 1
        assert "".join(chunks).count("x") >= 1000 - 100
