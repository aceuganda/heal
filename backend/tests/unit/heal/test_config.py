"""Tests for environment-driven configuration.

The rule these guard is in docs/architecture-decisions.md: a missing endpoint
must fail with a message naming the variable to set, never with a silent
default pointing at someone else's server.
"""
import pytest

from heal import config
from heal.config import KnowledgeNotConfigured
from heal.config import require_knowledge_config


class TestKnowledgeConfig:
    def test_returns_url_and_key_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "QDRANT_URL", "https://vectors.example.org")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "secret")

        assert require_knowledge_config() == ("https://vectors.example.org", "secret")

    def test_a_missing_url_names_the_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "QDRANT_URL", "")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "secret")

        with pytest.raises(KnowledgeNotConfigured) as excinfo:
            require_knowledge_config()

        assert "QDRANT_URL" in str(excinfo.value)


class TestApiKeyIsRequiredOffTheComposeNetwork:
    """Qdrant has no authentication by default.

    A store only reachable across the compose network is not exposed by an
    empty key. One reachable over a network is, so the key is mandatory there.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "http://qdrant:6333",
            "http://localhost:6333",
            "http://127.0.0.1:6333",
        ],
    )
    def test_a_private_host_may_run_without_a_key(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        monkeypatch.setattr(config, "QDRANT_URL", url)
        monkeypatch.setattr(config, "QDRANT_API_KEY", "")

        assert require_knowledge_config() == (url, "")

    @pytest.mark.parametrize(
        "url",
        [
            "https://vectors.example.org",
            "http://10.0.0.5:6333",
            "http://qdrant.internal.example.org:6333",
        ],
    )
    def test_any_other_host_must_have_a_key(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        monkeypatch.setattr(config, "QDRANT_URL", url)
        monkeypatch.setattr(config, "QDRANT_API_KEY", "")

        with pytest.raises(KnowledgeNotConfigured) as excinfo:
            require_knowledge_config()

        assert "QDRANT_API_KEY" in str(excinfo.value)

    def test_a_hostname_merely_containing_localhost_is_not_private(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Substring matching here would be an authentication bypass."""
        monkeypatch.setattr(config, "QDRANT_URL", "http://localhost.evil.com:6333")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "")

        with pytest.raises(KnowledgeNotConfigured):
            require_knowledge_config()


class TestShippedDefaults:
    def test_retrieval_is_on_by_default(self) -> None:
        """Retrieval is the product.

        `make up` starts the vector store, so a default of off meant the admin
        screen refused to index anything on a stack that was working fine.
        Setting KNOWLEDGE_ENABLED=false remains supported for a deployment that
        deliberately runs without a store.
        """
        assert config.KNOWLEDGE_ENABLED is True

    def test_no_endpoint_has_a_baked_in_default(self) -> None:
        for name in ("TRANSLATION_EN_URL", "TRANSLATION_LUG_URL", "QDRANT_URL"):
            assert getattr(config, name) == "", f"{name} must default to empty"
