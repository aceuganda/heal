"""Tests for the retrieval ranking rules.

These encode the rules from docs/architecture-decisions.md as behaviour: the
pre-filter, the score floor, the diversity cap, and hybrid fusion. They are the
clinical-safety half of the module, so they are asserted, not assumed.
"""
import pytest

from heal import config
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.settings import RetrievalSettings
from heal.knowledge.store import QdrantKnowledgeStore
from heal.knowledge.store import select_context
from tests.unit.heal.knowledge.conftest import FakeQdrant
from tests.unit.heal.knowledge.conftest import make_point


def build(client: FakeQdrant, embedder) -> QdrantKnowledgeStore:
    return QdrantKnowledgeStore(
        client=client, embedder=embedder, collection="test_collection"
    )


class TestPreFilter:
    def test_filters_are_sent_to_qdrant_not_applied_afterwards(
        self, fake_client, fake_embedder
    ) -> None:
        """Post-filtering an HNSW result set silently returns fewer than k.

        The approved/current filter must reach Qdrant as a query filter.
        """
        fake_client.dense_results = [make_point()]
        build(fake_client, fake_embedder).search("dose of DTG")

        assert fake_client.searches, "no search was issued"
        for call in fake_client.searches:
            assert call.get("query_filter") is not None, "search had no pre-filter"

    def test_requests_top_k_candidates_not_the_context_size(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [make_point()]
        build(fake_client, fake_embedder).search("query")
        assert fake_client.searches[0]["limit"] == config.RETRIEVAL_TOP_K


class TestScoreFloor:
    def test_returns_nothing_when_everything_is_below_the_floor(
        self, fake_client, fake_embedder
    ) -> None:
        """The old pipeline always returned top-k regardless of quality."""
        fake_client.dense_results = [make_point(score=0.10), make_point("p2", 0.05)]

        outcome = build(fake_client, fake_embedder).search("obscure question")

        assert not outcome
        assert outcome.below_floor
        assert outcome.chunks == []

    def test_records_the_near_miss_so_the_floor_can_be_tuned(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [make_point(score=0.30)]
        outcome = build(fake_client, fake_embedder).search("q")
        assert outcome.best_score_before_floor == pytest.approx(0.30 * 0.6, abs=0.01)

    def test_keeps_results_at_or_above_the_floor(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        fake_client.dense_results = [make_point(score=0.35)]
        assert build(fake_client, fake_embedder).search("q")


class TestDiversityCap:
    def test_one_document_cannot_crowd_out_the_others(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        fake_client.dense_results = [
            make_point("a1", 0.95, source_id="src-1"),
            make_point("a2", 0.94, source_id="src-1"),
            make_point("a3", 0.93, source_id="src-1"),
            make_point("b1", 0.92, source_id="src-2"),
        ]

        outcome = build(fake_client, fake_embedder).search("q")

        by_source = [c.source.source_id for c in outcome.chunks]
        assert by_source.count("src-1") == config.MAX_CHUNKS_PER_SOURCE
        assert "src-2" in by_source, "the second source was crowded out"

    def test_highest_scoring_chunks_survive_the_cap(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        fake_client.dense_results = [
            make_point("a1", 0.95, source_id="s"),
            make_point("a2", 0.90, source_id="s"),
            make_point("a3", 0.85, source_id="s"),
        ]
        outcome = build(fake_client, fake_embedder).search("q")
        assert [c.chunk.chunk_id for c in outcome.chunks] == ["a1", "a2"]


class TestHybridSearch:
    def test_a_lexical_only_match_still_reaches_the_answer(
        self, fake_client, fake_embedder
    ) -> None:
        """Ranking risk #1: drug codes match as strings, not as concepts.

        A chunk found only by the sparse half must survive into the result.
        """
        fake_client.dense_results = []
        fake_client.sparse_results = [make_point("lex", 1.0, text="TDF/3TC/DTG")]

        outcome = build(fake_client, fake_embedder).search("TDF/3TC/DTG")

        assert outcome, "lexical-only match was dropped"
        assert outcome.chunks[0].sparse_score == 1.0
        assert outcome.chunks[0].dense_score == 0.0

    def test_a_chunk_found_by_both_outranks_one_found_by_either(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [
            make_point("both", 0.8),
            make_point("dense_only", 0.75, source_id="src-2"),
        ]
        fake_client.sparse_results = [make_point("both", 0.9)]

        outcome = build(fake_client, fake_embedder).search("500mg BD")

        assert outcome.chunks[0].chunk.chunk_id == "both"

    def test_disabling_hybrid_skips_the_sparse_search_entirely(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        fake_client.dense_results = [make_point()]
        build(fake_client, fake_embedder).search("q")
        assert len(fake_client.searches) == 1


class TestFailureIsNotAnException:
    def test_an_unreachable_store_degrades_instead_of_raising(
        self, fake_client, fake_embedder
    ) -> None:
        """A chat answer beats a 500. The agent decides what to say."""
        fake_client.raises = ConnectionError("qdrant unreachable")

        outcome = build(fake_client, fake_embedder).search("q")

        assert outcome.unavailable
        assert outcome.error == "ConnectionError"
        assert not outcome

    def test_an_empty_query_does_not_reach_the_store(
        self, fake_client, fake_embedder
    ) -> None:
        assert not build(fake_client, fake_embedder).search("   ")
        assert fake_client.searches == []


class TestPerRequestSettings:
    """Tuning travels as an argument, never as a write to the module config.

    The chat path passes nothing and must keep behaving exactly as it did; the
    admin playground passes a value that lives only as long as the call.
    """

    def test_omitting_settings_uses_the_deployment_constants(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        monkeypatch.setattr(config, "MIN_RETRIEVAL_SCORE", 0.5)
        fake_client.dense_results = [make_point(score=0.45)]
        assert not build(fake_client, fake_embedder).search("q")

    def test_a_lower_floor_for_one_call_admits_what_the_default_refused(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        monkeypatch.setattr(config, "MIN_RETRIEVAL_SCORE", 0.5)
        fake_client.dense_results = [make_point(score=0.45)]

        outcome = build(fake_client, fake_embedder).search(
            "q",
            settings=RetrievalSettings(hybrid_search=False, min_retrieval_score=0.4),
        )

        assert outcome
        assert config.MIN_RETRIEVAL_SCORE == 0.5, "the call wrote the module config"

    def test_the_settings_top_k_is_what_qdrant_is_asked_for(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [make_point()]
        build(fake_client, fake_embedder).search(
            "q", settings=RetrievalSettings(retrieval_top_k=7)
        )
        assert fake_client.searches[0]["limit"] == 7

    def test_turning_hybrid_off_for_one_call_skips_the_sparse_search(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [make_point()]
        build(fake_client, fake_embedder).search(
            "q", settings=RetrievalSettings(hybrid_search=False)
        )
        assert len(fake_client.searches) == 1
        assert config.HYBRID_SEARCH is True


class TestSelectContext:
    """The one implementation of floor, cap and context size.

    The playground reports against this function rather than repeating its
    rules, so a screen cannot describe a pipeline the chat path did not run.
    """

    def test_it_reports_which_candidates_cleared_the_floor(self) -> None:
        settings = RetrievalSettings(min_retrieval_score=0.35, hybrid_search=False)
        candidates = [
            RetrievedChunk(chunk=_chunk("keep"), score=0.40),
            RetrievedChunk(chunk=_chunk("drop"), score=0.34),
        ]

        selection = select_context(candidates, settings)

        assert selection.passed_floor == frozenset({"keep"})

    def test_a_chunk_cut_by_the_cap_cleared_the_floor_first(self) -> None:
        settings = RetrievalSettings(
            min_retrieval_score=0.1, max_chunks_per_source=1, hybrid_search=False
        )
        candidates = [
            RetrievedChunk(chunk=_chunk("a1"), score=0.9),
            RetrievedChunk(chunk=_chunk("a2"), score=0.8),
        ]

        selection = select_context(candidates, settings)

        assert selection.passed_floor == frozenset({"a1", "a2"})
        assert selection.survived_cap == frozenset({"a1"})


def _chunk(chunk_id: str, source_id: str = "src-1"):
    from heal.knowledge.models import Chunk
    from heal.knowledge.models import SourceRef

    return Chunk(
        chunk_id=chunk_id,
        text="text",
        source=SourceRef(source_id=source_id, title="Guide"),
    )


class TestSources:
    def test_sources_are_distinct_and_in_citation_order(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "HYBRID_SEARCH", False)
        fake_client.dense_results = [
            make_point("a", 0.95, source_id="src-1", title="First"),
            make_point("b", 0.90, source_id="src-2", title="Second"),
            make_point("c", 0.85, source_id="src-1", title="First"),
        ]
        outcome = build(fake_client, fake_embedder).search("q")
        assert [s.source_id for s in outcome.sources] == ["src-1", "src-2"]

    def test_label_carries_publisher_and_year(self, fake_client, fake_embedder) -> None:
        fake_client.dense_results = [make_point(score=0.9)]
        outcome = build(fake_client, fake_embedder).search("q")
        label = outcome.chunks[0].source.label()
        assert "Uganda ART Guidelines" in label and "Ministry of Health" in label
