"""Tests for turning [1] markers into openable references.

The bug these exist to prevent: every citation the model wrote rendered as
literal `[1]` text pointing at nothing, because nothing ever extracted the
markers or mapped them to a passage.
"""
from heal.chat.citations import BLURB_CHARS
from heal.chat.citations import search_doc_fields
from heal.chat.citations import select_cited
from heal.chat.stream_processing import extract_citations
from heal.chat.stream_processing import StreamProcessor


class TestExtractCitations:
    def test_finds_a_single_marker(self) -> None:
        assert extract_citations("Give TDF/3TC/DTG once daily [1].") == [1]

    def test_returns_markers_in_order_of_first_appearance(self) -> None:
        """The reference list is rendered in this order, so it must be reading order."""
        text = "Cotrimoxazole is given [2]. The regimen is TDF/3TC/DTG [1], daily [2]."
        assert extract_citations(text) == [2, 1]

    def test_a_marker_repeated_is_listed_once(self) -> None:
        assert extract_citations("[1] and again [1] and [1]") == [1]

    def test_two_digit_markers_are_found(self) -> None:
        assert extract_citations("see [12]") == [12]

    def test_no_markers_yields_nothing(self) -> None:
        assert extract_citations("Take one tablet daily.") == []

    def test_empty_text_yields_nothing(self) -> None:
        assert extract_citations("") == []


class TestWhatMustNotMatch:
    """A marker regex that is too eager corrupts the answer text."""

    def test_a_markdown_link_is_not_a_citation(self) -> None:
        """`[1](http://...)` is a link, and treating it as a citation would
        turn the reference list into a list of URLs."""
        assert extract_citations("see [1](https://example.org/guide)") == []

    def test_bracketed_words_are_not_citations(self) -> None:
        assert extract_citations("[see below] and [note]") == []

    def test_an_unclosed_bracket_is_ignored(self) -> None:
        assert extract_citations("the dose [1 is unclear") == []

    def test_zero_is_not_a_valid_marker(self) -> None:
        """Markers are 1-based; [0] would index the passage before the first."""
        assert extract_citations("nonsense [0]") == []


class TestStreamProcessorIntegration:
    def test_citations_are_extracted_after_the_stream_finishes(self) -> None:
        processor = StreamProcessor()
        list(processor.process(["Give ", "TDF", " once daily ", "[1]", "."]))

        assert processor.result.citations == [1]

    def test_a_marker_split_across_tokens_is_still_found(self) -> None:
        """The reason extraction runs on the finished text, not per token.

        Providers routinely split "[12]" into three tokens; matching inside the
        loop would find nothing at all.
        """
        processor = StreamProcessor()
        list(processor.process(["The regimen ", "[", "12", "]", " applies."]))

        assert processor.result.citations == [12]

    def test_an_answer_with_no_citations_reports_none(self) -> None:
        processor = StreamProcessor()
        list(processor.process(["I cannot answer that."]))

        assert processor.result.citations == []

    def test_the_prefix_is_searched_too(self) -> None:
        """Emergency copy is prepended before the model runs and is part of
        the answer the reader sees."""
        processor = StreamProcessor(prefix="Call 912 now [1]. ")
        list(processor.process(["Then give oxygen."]))

        assert processor.result.citations == [1]


class FakeChunk:
    """Enough of a RetrievedChunk for the mapping logic."""

    def __init__(self, title: str, text: str, ordinal: int = 0) -> None:
        self.text = text
        self.score = 0.8
        self.dense_score = 0.9
        self.sparse_score = 0.2
        self.chunk = type("C", (), {"ordinal": ordinal})()
        self.source = type(
            "S",
            (),
            {
                "source_id": "src-1",
                "title": title,
                "version": "2023",
                "publisher": "MoH",
                "published": "2023",
                "label": lambda self: title,
            },
        )()


class TestSelectCited:
    """The 1-based mapping the whole reference UI rests on.

    Pure logic, no database: getting this wrong points a citation at the wrong
    guideline, which is worse than showing no citation at all.
    """

    def test_marker_one_maps_to_the_first_passage(self) -> None:
        chunks = [FakeChunk("First", "text one"), FakeChunk("Second", "text two")]
        paired = select_cited(chunks, [1])

        assert [n for n, _ in paired] == [1]
        assert paired[0][1].source.title == "First"

    def test_marker_two_maps_to_the_second_passage(self) -> None:
        chunks = [FakeChunk("First", "one"), FakeChunk("Second", "two")]
        assert select_cited(chunks, [2])[0][1].source.title == "Second"

    def test_only_cited_passages_are_returned(self) -> None:
        """The uncited ones would show sources the answer never leaned on."""
        chunks = [FakeChunk("A", "one"), FakeChunk("B", "two"), FakeChunk("C", "three")]
        paired = select_cited(chunks, [2])

        assert len(paired) == 1
        assert paired[0][1].source.title == "B"

    def test_citation_order_is_preserved(self) -> None:
        chunks = [FakeChunk("A", "one"), FakeChunk("B", "two")]
        assert [n for n, _ in select_cited(chunks, [2, 1])] == [2, 1]

    def test_a_marker_beyond_the_passages_is_dropped(self) -> None:
        """Models invent [9] when given five passages; it must point at nothing."""
        paired = select_cited([FakeChunk("A", "one")], [1, 9])

        assert [n for n, _ in paired] == [1]

    def test_a_zero_marker_is_dropped(self) -> None:
        assert select_cited([FakeChunk("A", "one")], [0]) == []

    def test_no_citations_selects_nothing(self) -> None:
        assert select_cited([FakeChunk("A", "one")], []) == []

    def test_no_passages_selects_nothing(self) -> None:
        """An unsourced answer must not fabricate a reference."""
        assert select_cited([], [1]) == []


class TestSearchDocFields:
    """What the drawer and the gloss are built from."""

    def test_the_full_passage_is_kept_for_the_drawer(self) -> None:
        chunk = FakeChunk("Guide", "Give TDF/3TC/DTG once daily in the evening.")
        fields = search_doc_fields(chunk)

        assert fields["match_highlights"] == [
            "Give TDF/3TC/DTG once daily in the evening."
        ]

    def test_version_is_part_of_the_document_identity(self) -> None:
        """Two editions of one guideline are different sources clinically."""
        assert search_doc_fields(FakeChunk("Guide", "text"))["document_id"] == (
            "src-1:2023"
        )

    def test_the_blurb_is_truncated_for_display(self) -> None:
        chunk = FakeChunk("Guide", "x" * 5000)
        assert len(search_doc_fields(chunk)["blurb"]) == BLURB_CHARS

    def test_scores_are_recorded_so_a_citation_can_be_explained(self) -> None:
        meta = search_doc_fields(FakeChunk("Guide", "text"))["doc_metadata"]
        assert "dense_score" in meta and "sparse_score" in meta
        assert meta["version"] == "2023"
