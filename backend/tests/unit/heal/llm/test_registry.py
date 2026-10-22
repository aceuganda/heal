"""Tests for model selection."""
import pytest

from heal import config
from heal.llm.registry import all_models
from heal.llm.registry import available_models
from heal.llm.registry import classifier_model
from heal.llm.registry import default_model
from heal.llm.registry import get_model


@pytest.fixture(autouse=True)
def openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENABLED_CHAT_MODELS", "")


class TestCatalogue:
    def test_ids_are_unique(self) -> None:
        ids = [m.id for m in all_models()]
        assert len(ids) == len(set(ids))

    def test_unknown_model_lists_what_exists(self) -> None:
        with pytest.raises(ValueError, match="gpt-4o-mini"):
            get_model("no-such-model")

    def test_api_key_env_follows_the_provider(self) -> None:
        assert get_model("gpt-4o").api_key_env == "OPENAI_API_KEY"
        assert get_model("claude-sonnet-4-5").api_key_env == "ANTHROPIC_API_KEY"

    def test_configured_defaults_resolve(self) -> None:
        assert default_model().id == config.CHAT_MODEL
        assert classifier_model().id == config.CLASSIFIER_MODEL


class TestAvailability:
    def test_hides_models_whose_provider_has_no_key(self) -> None:
        ids = {m.id for m in available_models()}
        assert "gpt-4o" in ids
        assert "claude-sonnet-4-5" not in ids

    def test_shows_a_provider_once_its_key_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        assert "claude-sonnet-4-5" in {m.id for m in available_models()}

    def test_accepts_the_inherited_openai_key_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing deployments store the key as GEN_AI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("GEN_AI_API_KEY", "test-key")
        assert "gpt-4o" in {m.id for m in available_models()}

    def test_non_selectable_models_are_never_offered(self) -> None:
        """gpt-3.5-turbo is kept as an eval baseline, not as a user choice."""
        assert "gpt-3.5-turbo" not in {m.id for m in available_models()}
        assert "gpt-3.5-turbo" in {m.id for m in all_models()}

    def test_allowlist_narrows_the_offer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "ENABLED_CHAT_MODELS", "gpt-4o-mini")
        assert {m.id for m in available_models()} == {"gpt-4o-mini"}
