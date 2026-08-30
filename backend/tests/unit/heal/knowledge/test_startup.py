"""Tests for the boot-time preparation of the knowledge store.

What is being pinned: preparation happens at startup so the first upload does
not pay for it, and a store that is not up yet never takes the API down with
it -- Qdrant and the API start together, so on a cold `make up` the API will
sometimes win the race.
"""
import pytest

from heal import config
from heal.knowledge import startup


class Recorder:
    def __init__(self, raises: Exception | None = None) -> None:
        self.calls = 0
        self.raises = raises

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls += 1
        if self.raises:
            raise self.raises


class FakeEmbedder:
    def __init__(self, raises: Exception | None = None) -> None:
        self.queries: list[str] = []
        self.raises = raises

    def embed_query(self, text: str) -> list[float]:
        if self.raises:
            raise self.raises
        self.queries.append(text)
        return [0.0]


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    """Swap both halves of the preparation for recorders."""
    from heal.knowledge import embedder as embedder_module
    from heal.knowledge import store as store_module

    ensure = Recorder()
    embedder = FakeEmbedder()
    monkeypatch.setattr(store_module, "ensure_collection", ensure)
    monkeypatch.setattr(embedder_module, "get_embedder", lambda: embedder)
    return ensure, embedder


class TestPreparation:
    def test_it_creates_the_collection_and_loads_the_model(self, patched) -> None:
        ensure, embedder = patched

        startup.prepare_knowledge_store()

        assert ensure.calls == 1
        assert embedder.queries, "the model is loaded, not merely constructed"

    def test_an_unreachable_store_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Qdrant may still be starting; the first ingest creates it instead."""
        from heal.knowledge import embedder as embedder_module
        from heal.knowledge import store as store_module

        monkeypatch.setattr(
            store_module, "ensure_collection", Recorder(ConnectionError("refused"))
        )
        embedder = FakeEmbedder()
        monkeypatch.setattr(embedder_module, "get_embedder", lambda: embedder)

        startup.prepare_knowledge_store()

        # The model still loads: the two failures are independent.
        assert embedder.queries

    def test_a_model_that_will_not_load_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from heal.knowledge import embedder as embedder_module
        from heal.knowledge import store as store_module

        ensure = Recorder()
        monkeypatch.setattr(store_module, "ensure_collection", ensure)
        monkeypatch.setattr(
            embedder_module,
            "get_embedder",
            lambda: FakeEmbedder(OSError("no such model")),
        )

        startup.prepare_knowledge_store()

        assert ensure.calls == 1


class TestBackgroundStart:
    def test_nothing_is_prepared_when_retrieval_is_off(
        self, monkeypatch: pytest.MonkeyPatch, patched
    ) -> None:
        ensure, embedder = patched
        monkeypatch.setattr(config, "KNOWLEDGE_ENABLED", False)

        startup.prepare_knowledge_store_in_background()

        assert ensure.calls == 0

    def test_preparation_runs_off_the_boot_path(
        self, monkeypatch: pytest.MonkeyPatch, patched
    ) -> None:
        """Boot must not block on a model load or a store that is not up."""
        ensure, _ = patched
        monkeypatch.setattr(config, "KNOWLEDGE_ENABLED", True)
        started: list[str] = []

        class FakeThread:
            def __init__(self, target, name, daemon) -> None:
                self.target = target
                self.daemon = daemon
                started.append(name)

            def start(self) -> None:
                self.target()

        monkeypatch.setattr(startup.threading, "Thread", FakeThread)

        startup.prepare_knowledge_store_in_background()

        assert started == ["knowledge-warmup"]
        assert ensure.calls == 1
