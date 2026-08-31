"""Tests for the admin-facing store operations."""
from heal.knowledge.store import collection_stats
from heal.knowledge.store import list_sources
from tests.unit.heal.knowledge.conftest import make_point


class FakeScrollClient:
    """Adds scroll/get_collection/delete to the shared fake."""

    def __init__(self, pages, exists: bool = True) -> None:
        self.pages = pages
        self.deletes = []
        self.exists = exists

    def collection_exists(self, name) -> bool:
        return self.exists

    def scroll(self, **kwargs):
        offset = kwargs.get("offset") or 0
        if offset >= len(self.pages):
            return [], None
        nxt = offset + 1
        return self.pages[offset], (nxt if nxt < len(self.pages) else None)

    def delete(self, **kwargs):
        self.deletes.append(kwargs)

    def get_collection(self, name):
        class Info:
            points_count = 42

        return Info()


class TestListSources:
    def test_chunks_are_aggregated_into_one_row_per_version(self) -> None:
        client = FakeScrollClient(
            [
                [
                    make_point("a", source_id="s1", title="Guide"),
                    make_point("b", source_id="s1", title="Guide"),
                ]
            ]
        )
        sources = list_sources(client=client, collection="c")
        assert len(sources) == 1
        assert sources[0]["chunks"] == 2

    def test_versions_of_one_source_are_listed_separately(self) -> None:
        client = FakeScrollClient(
            [
                [
                    make_point("a", source_id="s1", title="Guide", version="2022"),
                    make_point("b", source_id="s1", title="Guide", version="2024"),
                ]
            ]
        )
        assert len(list_sources(client=client, collection="c")) == 2

    def test_a_partly_approved_source_reads_as_not_approved(self) -> None:
        """A half-applied approval should look wrong, not approved."""
        approved = make_point("a", source_id="s1")
        unapproved = make_point("b", source_id="s1")
        unapproved.payload["approved"] = False
        client = FakeScrollClient([[approved, unapproved]])
        assert list_sources(client=client, collection="c")[0]["approved"] is False

    def test_paging_continues_until_the_cursor_is_exhausted(self) -> None:
        client = FakeScrollClient(
            [
                [make_point("a", source_id="s1")],
                [make_point("b", source_id="s2", title="Second")],
            ]
        )
        assert len(list_sources(client=client, collection="c")) == 2

    def test_an_empty_collection_lists_nothing(self) -> None:
        assert list_sources(client=FakeScrollClient([]), collection="c") == []

    def test_a_collection_that_does_not_exist_yet_lists_nothing(self) -> None:
        """A stack whose first document has not been uploaded is not an error.

        Scrolling a collection Qdrant has never been asked to create raises,
        and that 500 reached the admin screen as a blank page.
        """
        client = FakeScrollClient([], exists=False)
        assert list_sources(client=client, collection="c") == []


class TestStats:
    def test_stats_expose_the_tuning_constants_the_admin_screen_shows(self) -> None:
        stats = collection_stats(client=FakeScrollClient([]), collection="c")
        assert stats["points"] == 42
        assert stats["collection_exists"] is True

    def test_stats_report_zero_before_the_collection_exists(self) -> None:
        """The status panel must render on a stack that has indexed nothing."""
        client = FakeScrollClient([], exists=False)
        stats = collection_stats(client=client, collection="c")

        assert stats["collection_exists"] is False
        assert stats["points"] == 0
        assert stats["embedding_dim"]  # tuning constants still reported
        for key in (
            "min_retrieval_score",
            "context_top_k",
            "max_chunks_per_source",
            "embedding_model",
            "hybrid_search",
        ):
            assert key in stats
