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


class TestQueryApi:
    """The 1.19 client removed `search`. These pin the replacement.

    Worth asserting rather than trusting: the call still type-checks against a
    permissive fake if someone reverts it, and the failure would only appear
    against a real Qdrant.
    """

    def test_both_halves_go_through_query_points(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.dense_results = [make_point()]
        fake_client.sparse_results = [make_point("lex", 0.5)]

        build(fake_client, fake_embedder).search("TDF/3TC/DTG")

        assert not hasattr(
            fake_client, "search"
        ), "the fake still offers a method the 1.19 client does not have"
        assert [c["using"] for c in fake_client.searches] == ["dense", "lexical"]

    def test_the_sparse_half_is_addressed_by_name_not_by_tuple(
        self, fake_client, fake_embedder
    ) -> None:
        """`query_points` names the vector in `using`, never in `query`."""
        fake_client.dense_results = []
        fake_client.sparse_results = [make_point("lex", 0.5)]

        build(fake_client, fake_embedder).search("500mg BD")

        sparse_call = fake_client.searches[-1]
        assert sparse_call["using"] == "lexical"
        assert not isinstance(sparse_call["query"], tuple)


class TestIdfModifier:
    """Corpus statistics for the lexical half. See "The IDF gap" in the doc."""

    def test_a_new_collection_declares_the_idf_modifier(
        self, fake_client, monkeypatch
    ) -> None:
        from qdrant_client import models as qm

        from heal.knowledge import store as store_module

        monkeypatch.setattr(config, "SPARSE_IDF", True)
        monkeypatch.setattr(config, "QDRANT_COLLECTION", "fresh")

        store_module.ensure_collection(client=fake_client, dimension=384)

        sparse = fake_client.created["sparse_vectors_config"]["lexical"]
        assert sparse.modifier == qm.Modifier.IDF

    def test_the_modifier_is_omitted_when_idf_is_disabled(
        self, fake_client, monkeypatch
    ) -> None:
        from heal.knowledge import store as store_module

        monkeypatch.setattr(config, "SPARSE_IDF", False)
        monkeypatch.setattr(config, "QDRANT_COLLECTION", "fresh")

        store_module.ensure_collection(client=fake_client, dimension=384)

        sparse = fake_client.created["sparse_vectors_config"]["lexical"]
        assert getattr(sparse, "modifier", None) is None

    def test_an_existing_collection_without_idf_is_reported_not_silently_kept(
        self, fake_client, monkeypatch, caplog
    ) -> None:
        """The silent-failure case this guard exists for.

        The modifier can only be set at creation. Turning the flag on against
        an older collection changes nothing, so without this warning an admin
        would read "IDF: on" in the panel while rare drug codes went on being
        under-weighted.
        """
        from heal.knowledge import store as store_module

        monkeypatch.setattr(config, "SPARSE_IDF", True)
        monkeypatch.setattr(config, "QDRANT_COLLECTION", "existing")
        fake_client.collections.add("existing")
        fake_client.live_modifier = None

        with caplog.at_level("WARNING"):
            store_module.ensure_collection(client=fake_client)

        assert "re-ingest" in caplog.text.lower()
        assert not hasattr(fake_client, "created"), "an existing collection was rebuilt"

    def test_a_matching_collection_says_nothing_alarming(
        self, fake_client, monkeypatch, caplog
    ) -> None:
        from heal.knowledge import store as store_module

        monkeypatch.setattr(config, "SPARSE_IDF", True)
        monkeypatch.setattr(config, "QDRANT_COLLECTION", "existing")
        fake_client.collections.add("existing")
        fake_client.live_modifier = "idf"

        with caplog.at_level("WARNING"):
            store_module.ensure_collection(client=fake_client)

        assert caplog.text == ""

    def test_stats_separate_what_is_configured_from_what_is_running(
        self, fake_client, monkeypatch
    ) -> None:
        from heal.knowledge import store as store_module

        monkeypatch.setattr(config, "SPARSE_IDF", True)
        fake_client.collections.add("kb")
        fake_client.live_modifier = None

        stats = store_module.collection_stats(client=fake_client, collection="kb")

        assert stats["sparse_idf_configured"] is True
        assert stats["sparse_idf_active"] is False
        assert stats["sparse_idf_needs_reingest"] is True


class TestSparseRescaling:
    """What IDF does to the fused score, and why clamping is not enough."""

    def test_idf_scores_above_one_keep_their_order_instead_of_saturating(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        """The bug this guards against.

        IDF multiplies each term by roughly log(N / df), so a rare drug code
        can push the dot product to 8 or more. Clamping to 1.0 would flatten
        every lexical hit to the same value and throw away the ordering IDF was
        enabled to produce.
        """
        monkeypatch.setattr(config, "SPARSE_IDF", True)
        fake_client.dense_results = []
        fake_client.sparse_results = [
            make_point("strong", 8.4, source_id="src-1"),
            make_point("weak", 2.1, source_id="src-2"),
        ]

        found = build(fake_client, fake_embedder).candidates("TDF/3TC/DTG")

        by_id = {c.chunk.chunk_id: c for c in found}
        assert by_id["strong"].score > by_id["weak"].score, "scores saturated"
        assert by_id["weak"].score > 0.0

    def test_the_raw_sparse_score_is_still_reported_unmodified(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        """Normalisation is for fusion only.

        The admin playground explains a ranking with these numbers, so the
        value Qdrant returned has to survive to the surface.
        """
        monkeypatch.setattr(config, "SPARSE_IDF", True)
        fake_client.dense_results = []
        fake_client.sparse_results = [make_point("s", 8.4)]

        found = build(fake_client, fake_embedder).candidates("q")

        assert found[0].sparse_score == 8.4

    def test_pre_idf_scoring_is_unchanged(
        self, fake_client, fake_embedder, monkeypatch
    ) -> None:
        """With IDF off the fusion must be arithmetically what it always was."""
        monkeypatch.setattr(config, "SPARSE_IDF", False)
        monkeypatch.setattr(config, "HYBRID_ALPHA", 0.6)
        fake_client.dense_results = [make_point("a", 0.8)]
        fake_client.sparse_results = [make_point("a", 0.5)]

        found = build(fake_client, fake_embedder).candidates("q")

        assert found[0].score == pytest.approx(0.6 * 0.8 + 0.4 * 0.5)
