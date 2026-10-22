"""Translation provider registry.

Call sites ask the registry for the configured provider; they never name an
implementation. Swapping the private MT services for a hosted model is then a
change to TRANSLATION_PROVIDER, not a change to the chat flow.
"""
from heal import config
from heal.language.errors import TranslationNotConfigured
from heal.language.providers.base import TranslationProvider
from heal.language.providers.heal_mt import HealMtProvider

_PROVIDERS: dict[str, type[TranslationProvider]] = {
    HealMtProvider.name: HealMtProvider,
}


def register_provider(provider: type[TranslationProvider]) -> None:
    """Add a provider to the registry. Intended for tests and future backends."""
    _PROVIDERS[provider.name] = provider


def build_provider(name: str | None = None) -> TranslationProvider:
    """Instantiate the named provider, defaulting to the configured one."""
    key = (name or config.TRANSLATION_PROVIDER).strip()
    try:
        return _PROVIDERS[key]()
    except KeyError:
        raise TranslationNotConfigured(
            f"Unknown TRANSLATION_PROVIDER '{key}'. "
            f"Available: {', '.join(sorted(_PROVIDERS))}"
        ) from None


__all__ = ["TranslationProvider", "build_provider", "register_provider"]
