"""Shared fixtures for the `heal` unit tests.

The one thing here is the saved-settings lookup. `GenerationSettings()` and
`default_model()` both read `heal.llm.defaults`, which reaches the database for
the deployment's saved overrides. In a unit test there is no database, and the
module's own fallback -- log it and use the environment -- is exactly right in
production and exactly wrong here: every construction would attempt a
connection, wait for it to fail, and log a warning.

So the lookup is stubbed empty by default, which means "nothing saved, follow
the environment". A test that is about saved settings overrides the stub
itself; see tests/unit/heal/llm/test_defaults.py.
"""
import pytest

from heal.llm import defaults
from heal.llm import registry


@pytest.fixture(autouse=True)
def no_saved_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is saved: every knob follows the environment."""
    defaults.invalidate()
    monkeypatch.setattr(defaults, "stored", lambda refresh=False: {})
    monkeypatch.setattr(defaults, "last_change", lambda: (None, None))


@pytest.fixture(autouse=True)
def no_openai_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI's live model list is empty: no test ever reaches the network.

    A test about the listing stubs `_fetch_openai_models` itself.
    """
    monkeypatch.setattr(registry, "_fetch_openai_models", lambda key: [])
    monkeypatch.setitem(registry._openai_cache, "ttl", 0.0)
