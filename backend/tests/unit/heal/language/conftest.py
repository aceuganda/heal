"""Shared fixtures for language tests.

Nothing here touches the network. The provider is exercised against fake HTTP
responses so the suite runs identically on a laptop and in CI.
"""
import pytest

from heal import config


@pytest.fixture(autouse=True)
def fast_and_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the provider at a fake host and strip every deliberate delay.

    The stream pacing and retry backoff exist for humans, not for tests; leaving
    them in would add seconds per case for no extra coverage.
    """
    monkeypatch.setattr(config, "TRANSLATION_EN_URL", "http://mt-en.test")
    monkeypatch.setattr(config, "TRANSLATION_LUG_URL", "http://mt-lug.test")
    monkeypatch.setattr(config, "TRANSLATION_API_KEY", "")
    monkeypatch.setattr(config, "TRANSLATION_STREAM_DELAY", 0.0)
    monkeypatch.setattr(config, "TRANSLATION_RETRY_BACKOFF", 0.0)
    monkeypatch.setattr(config, "TRANSLATION_MAX_RETRIES", 2)


class FakeResponse:
    """Minimal stand-in for `requests.Response`."""

    def __init__(self, status_code: int = 200, text: str = "", chunks=None) -> None:
        self.status_code = status_code
        self.text = text
        self._chunks = chunks or []

    def iter_content(self, chunk_size: int = 1024):
        yield from self._chunks


@pytest.fixture
def fake_response():
    return FakeResponse
