"""Tests for the LanguageService facade and the provider registry."""
import pytest

from heal import config
from heal.language.errors import TranslationNotConfigured
from heal.language.providers import build_provider
from heal.language.providers import register_provider
from heal.language.providers.base import TranslationProvider
from heal.language.service import LanguageService


class StubProvider(TranslationProvider):
    """Records what it was asked to translate, so call sites can be asserted."""

    name = "stub"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def to_english(self, text: str) -> str:
        self.seen.append(text)
        return f"EN({text})"

    def to_luganda(self, text: str) -> str:
        self.seen.append(text)
        return f"LUG({text})"

    def stream_to_luganda(self, text: str):
        self.seen.append(text)
        yield from ["LUG(", text, ")"]

    async def astream_to_luganda(self, text: str):
        self.seen.append(text)
        for part in ["LUG(", text, ")"]:
            yield part


class TestLanguageDetection:
    @pytest.mark.parametrize("value", ["luganda", "Luganda", "  LUGANDA  "])
    def test_recognised_forms(self, value: str) -> None:
        assert LanguageService.is_luganda(value) is True

    @pytest.mark.parametrize("value", ["english", "", None, "lug"])
    def test_everything_else_is_english(self, value: str | None) -> None:
        assert LanguageService.is_luganda(value) is False


class TestDelegation:
    def test_each_direction_reaches_the_provider(self) -> None:
        provider = StubProvider()
        service = LanguageService(provider=provider)

        assert service.to_english("ki kigambo") == "EN(ki kigambo)"
        assert service.to_luganda("one tablet") == "LUG(one tablet)"
        assert "".join(service.stream_to_luganda("two tablets")) == "LUG(two tablets)"
        assert provider.seen == ["ki kigambo", "one tablet", "two tablets"]

    @pytest.mark.asyncio
    async def test_async_stream_reaches_the_provider(self) -> None:
        service = LanguageService(provider=StubProvider())
        tokens = [t async for t in service.astream_to_luganda("one tablet")]
        assert "".join(tokens) == "LUG(one tablet)"


class TestRegistry:
    def test_default_provider_is_the_configured_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TRANSLATION_PROVIDER", "heal_mt")
        assert build_provider().name == "heal_mt"

    def test_unknown_provider_lists_what_is_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TRANSLATION_PROVIDER", "nope")
        with pytest.raises(TranslationNotConfigured, match="heal_mt"):
            build_provider()

    def test_a_new_backend_needs_no_call_site_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Swapping MT backends is a config change, which is the whole point."""
        register_provider(StubProvider)
        monkeypatch.setattr(config, "TRANSLATION_PROVIDER", "stub")
        assert LanguageService().to_english("ki kigambo") == "EN(ki kigambo)"
