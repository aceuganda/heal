"""References the model names when the library has nothing.

The safety line these tests hold is that the two kinds of citation never mix. A
library citation points at words an administrator approved and we hold; an
external one points at a name the model produced. A reader who cannot tell them
apart has been misled about where a dose came from, so the parser refuses to
run at all when there were passages -- and the drawer, elsewhere, says which is
which.
"""
from heal.chat import external_refs


ANSWER = """\
Yellow fever is prevented by a single dose of the live attenuated vaccine [1].
Uganda includes it in the routine schedule at nine months [2].

Sources
[1] WHO
[2] Uganda Clinical Guidelines
"""


class TestParsing:
    def test_the_block_is_read_when_there_were_no_passages(self) -> None:
        refs = external_refs.parse(ANSWER, has_passages=False)
        assert [r.name for r in refs.values()] == ["WHO", "Uganda Clinical Guidelines"]

    def test_markers_key_the_references(self) -> None:
        refs = external_refs.parse(ANSWER, has_passages=False)
        assert refs[1].name == "WHO"
        assert refs[2].name == "Uganda Clinical Guidelines"

    def test_the_answer_itself_is_never_rewritten(self) -> None:
        # `parse` returns references only. Editing the text would leave what
        # was streamed and what was stored saying different things -- and it
        # would be a program silently editing a clinical answer.
        before = ANSWER
        external_refs.parse(ANSWER, has_passages=False)
        assert ANSWER == before

    def test_a_references_heading_is_read_too(self) -> None:
        text = "Answer [1].\n\nReferences:\n[1] WHO\n"
        assert external_refs.parse(text, has_passages=False)[1].name == "WHO"

    def test_markdown_decoration_around_the_heading_is_tolerated(self) -> None:
        text = "Answer [1].\n\n**Sources**\n[1] WHO\n"
        assert external_refs.parse(text, has_passages=False)[1].name == "WHO"

    def test_a_bulleted_entry_is_tolerated(self) -> None:
        text = "Answer [1].\n\nSources\n- [1] WHO\n"
        assert external_refs.parse(text, has_passages=False)[1].name == "WHO"

    def test_prose_after_the_block_ends_it(self) -> None:
        text = "Answer [1].\n\nSources\n[1] WHO\n\nCheck local protocol first.\n"
        refs = external_refs.parse(text, has_passages=False)
        assert list(refs) == [1]

    def test_the_word_sources_mid_answer_is_not_a_block(self) -> None:
        text = "Two sources agree on this. There is no list here.\n"
        assert external_refs.parse(text, has_passages=False) == {}

    def test_an_answer_with_no_block_yields_nothing(self) -> None:
        assert external_refs.parse("Just an answer.\n", has_passages=False) == {}

    def test_an_empty_answer_yields_nothing(self) -> None:
        assert external_refs.parse("", has_passages=False) == {}


class TestTheTwoKindsNeverMix:
    def test_nothing_is_parsed_when_the_answer_had_passages(self) -> None:
        # With passages in hand, marker N means passage N. A block of
        # model-named sources numbered alongside them would point a reader at
        # the wrong thing -- at a dose from the wrong guideline.
        assert external_refs.parse(ANSWER, has_passages=True) == {}


class TestLimits:
    def test_a_long_list_is_capped(self) -> None:
        entries = "\n".join(f"[{n}] Source {n}" for n in range(1, 12))
        refs = external_refs.parse(f"A.\n\nSources\n{entries}\n", has_passages=False)
        assert len(refs) == external_refs.MAX_REFS

    def test_a_repeated_marker_keeps_the_first(self) -> None:
        text = "A [1].\n\nSources\n[1] WHO\n[1] CDC\n"
        assert external_refs.parse(text, has_passages=False)[1].name == "WHO"

    def test_a_paragraph_wearing_a_citation_is_truncated(self) -> None:
        long_name = "W" * 500
        text = f"A [1].\n\nSources\n[1] {long_name}\n"
        name = external_refs.parse(text, has_passages=False)[1].name
        assert len(name) <= external_refs.MAX_NAME_CHARS + 1

    def test_an_entry_with_no_name_is_dropped(self) -> None:
        assert external_refs.parse("A.\n\nSources\n[1]\n", has_passages=False) == {}

    def test_trailing_punctuation_is_cleaned_off_the_name(self) -> None:
        text = "A [1].\n\nSources\n[1] *WHO*.\n"
        assert external_refs.parse(text, has_passages=False)[1].name == "WHO"


class TestStoredShape:
    """What an external reference looks like once it is a row.

    Empty where a library citation has substance, and flagged, because the
    drawer and the gloss endpoint both decide what to show from these fields.
    """

    def test_it_carries_no_passage_and_no_excerpt(self) -> None:
        from heal.chat.citations import external_doc_fields

        fields = external_doc_fields(external_refs.ExternalRef(1, "WHO"))
        assert fields["blurb"] == ""
        assert fields["match_highlights"] == []

    def test_it_carries_no_link(self) -> None:
        # A URL nobody fetched is a claim about what is at the other end of it.
        from heal.chat.citations import external_doc_fields

        assert external_doc_fields(external_refs.ExternalRef(1, "WHO"))["link"] is None

    def test_it_is_flagged_as_external(self) -> None:
        from heal.chat.citations import EXTERNAL_FLAG
        from heal.chat.citations import external_doc_fields

        fields = external_doc_fields(external_refs.ExternalRef(1, "WHO"))
        assert fields["doc_metadata"][EXTERNAL_FLAG] == "true"

    def test_the_name_is_what_the_drawer_will_show(self) -> None:
        from heal.chat.citations import external_doc_fields

        fields = external_doc_fields(external_refs.ExternalRef(1, "WHO"))
        assert fields["semantic_id"] == "WHO"
