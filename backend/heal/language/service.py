"""LanguageService -- the single entry point for translation.

Design A: Luganda is translated to English on the way in and back to Luganda on
the way out. Everything between those two points -- retrieval, ranking, the
model call -- happens in English only.

Call sites use this facade rather than a provider directly, so that the choice
of backend, the timeouts and the failure behaviour live in one place.
"""
from collections.abc import AsyncIterator
from collections.abc import Iterator
from functools import lru_cache

from heal.language.providers import build_provider
from heal.language.providers import TranslationProvider

LUGANDA = "luganda"
ENGLISH = "english"


class LanguageService:
    """Translates chat text between the user's language and English."""

    def __init__(self, provider: TranslationProvider | None = None) -> None:
        self._provider = provider or build_provider()

    @staticmethod
    def is_luganda(language: str | None) -> bool:
        """The one place the language flag is interpreted."""
        return (language or "").strip().lower() == LUGANDA

    def to_english(self, text: str) -> str:
        return self._provider.to_english(text)

    def to_luganda(self, text: str) -> str:
        return self._provider.to_luganda(text)

    def stream_to_luganda(self, text: str) -> Iterator[str]:
        """Yield the Luganda translation token by token, already paced."""
        yield from self._provider.stream_to_luganda(text)

    async def astream_to_luganda(self, text: str) -> AsyncIterator[str]:
        async for token in self._provider.astream_to_luganda(text):
            yield token


@lru_cache(maxsize=1)
def get_language_service() -> LanguageService:
    """Process-wide instance. Providers are stateless, so sharing one is safe."""
    return LanguageService()
