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
        monkeypatch.setattr(config, "QDRANT_URL", "http://qdrant.test:6333")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "secret")

        assert require_knowledge_config() == ("http://qdrant.test:6333", "secret")

    @pytest.mark.parametrize(
        ("url", "key", "expected"),
        [
            ("", "secret", "QDRANT_URL"),
            ("http://qdrant.test:6333", "", "QDRANT_API_KEY"),
        ],
    )
    def test_names_the_missing_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
        key: str,
        expected: str,
    ) -> None:
        monkeypatch.setattr(config, "QDRANT_URL", url)
        monkeypatch.setattr(config, "QDRANT_API_KEY", key)

        with pytest.raises(KnowledgeNotConfigured) as excinfo:
            require_knowledge_config()

        assert expected in str(excinfo.value)

    def test_names_both_when_neither_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Phase 1 default. Retrieval is off, so this is never reached --
        but if it is, the operator should not have to guess twice."""
        monkeypatch.setattr(config, "QDRANT_URL", "")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "")

        with pytest.raises(KnowledgeNotConfigured) as excinfo:
            require_knowledge_config()

        message = str(excinfo.value)
        assert "QDRANT_URL" in message and "QDRANT_API_KEY" in message

    def test_an_empty_key_is_never_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Qdrant runs unauthenticated by default; an empty key must be an
        error rather than a working connection to an open vector store."""
        monkeypatch.setattr(config, "QDRANT_URL", "http://qdrant.test:6333")
        monkeypatch.setattr(config, "QDRANT_API_KEY", "")

        with pytest.raises(KnowledgeNotConfigured):
            require_knowledge_config()


class TestPhase1Defaults:
    def test_retrieval_is_off_by_default(self) -> None:
        """KNOWLEDGE_ENABLED=false must be the shipped default, so that cutting
        Phase 2 on Day 8 needs no rollback."""
        assert config.KNOWLEDGE_ENABLED is False

    def test_no_endpoint_has_a_baked_in_default(self) -> None:
        for name in ("TRANSLATION_EN_URL", "TRANSLATION_LUG_URL", "QDRANT_URL"):
            assert getattr(config, name) == "", f"{name} must default to empty"
