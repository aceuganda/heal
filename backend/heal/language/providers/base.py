"""The contract every translation backend implements.

Kept deliberately small: two directions, each available as a whole-string call
and as a token stream. Anything a provider cannot do it declares by raising
NotImplementedError, and the service layer degrades rather than crashing.
"""
import abc
from collections.abc import AsyncIterator
from collections.abc import Iterator


class TranslationProvider(abc.ABC):
    """Translates between English and Luganda."""

    # Registry key, also the value of TRANSLATION_PROVIDER.
    name: str = ""

    @abc.abstractmethod
    def to_english(self, text: str) -> str:
        """Luganda in, English out. Blocking."""

    @abc.abstractmethod
    def to_luganda(self, text: str) -> str:
        """English in, Luganda out. Blocking."""

    @abc.abstractmethod
    def stream_to_luganda(self, text: str) -> Iterator[str]:
        """English in, Luganda out, yielded token by token."""

    async def astream_to_luganda(self, text: str) -> AsyncIterator[str]:
        """Async form of `stream_to_luganda`, for endpoints on the event loop."""
        raise NotImplementedError(
            f"{type(self).__name__} has no async streaming implementation"
        )
        yield ""  # pragma: no cover - makes this an async generator
