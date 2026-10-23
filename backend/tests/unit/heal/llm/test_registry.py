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


class TestOpenAIListing:
    """OpenAI's own model list, read with the key the client already uses."""

    @pytest.fixture
    def listing(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        from heal.llm import registry

        calls: list[str] = []

        def fetch(key: str) -> list[str]:
            calls.append(key)
            return ["gpt-4.1", "gpt-4o", "text-embedding-3-small", "gpt-4o-audio-preview"]

        monkeypatch.setattr(registry, "_openai_key", lambda: "test-key")
        monkeypatch.setattr(registry, "_fetch_openai_models", fetch)
        return calls

    def test_lists_chat_models_only(self, listing: list[str]) -> None:
        ids = {m.id for m in all_models()}
        assert "gpt-4.1" in ids
        assert "text-embedding-3-small" not in ids
        assert "gpt-4o-audio-preview" not in ids

    def test_listed_model_resolves(self, listing: list[str]) -> None:
        assert get_model("gpt-4.1").provider == "openai"

    def test_static_entry_wins_over_listed(self, listing: list[str]) -> None:
        assert get_model("gpt-4o").display_name == "GPT-4o"

    def test_known_ids_never_trigger_a_listing(self, listing: list[str]) -> None:
        """Per-message lookups must not wait on OpenAI."""
        get_model("gpt-4o-mini")
        assert listing == []

    def test_listing_is_cached(self, listing: list[str]) -> None:
        from heal.llm import registry

        registry._openai_cache["ttl"] = 0.0
        all_models()
        all_models()
        assert len(listing) == 1

    def test_a_failed_listing_keeps_the_static_catalogue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from heal.llm import registry

        def broken(key: str) -> list[str]:
            raise ConnectionError("no network")

        monkeypatch.setattr(registry, "_openai_key", lambda: "test-key")
        monkeypatch.setattr(registry, "_fetch_openai_models", broken)
        assert "gpt-4o-mini" in {m.id for m in all_models()}

    def test_no_key_means_no_listing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from heal.llm import registry

        monkeypatch.setattr(registry, "_openai_key", lambda: None)
        monkeypatch.setattr(
            registry, "_fetch_openai_models", lambda key: pytest.fail("fetched")
        )
        all_models()


class TestClassifierFor:
    """The internal model understands the questions it answers."""

    def test_cloud_chat_keeps_the_configured_classifier(self) -> None:
        from heal.llm import classifier_for

        assert classifier_for("gpt-4o").id == config.CLASSIFIER_MODEL

    def test_self_hosted_chat_classifies_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from heal.llm import classifier_for

        monkeypatch.setattr(config, "SELF_HOSTED_URL", "http://internal.test/v1")
        monkeypatch.setattr(config, "SELF_HOSTED_MODEL", "local-model")
        assert classifier_for("self-hosted").self_hosted
