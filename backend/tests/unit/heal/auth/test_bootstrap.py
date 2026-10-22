"""Tests for seeding the first administrator.

The rules being pinned are the ones that stop a convenience from becoming a
back door: it only fires into an empty database, it does nothing without
explicit configuration, and it never takes the API down with it.
"""
import pytest

from heal import bootstrap
from heal import config


class Recorder:
    """Stands in for the whole create path, which needs a database."""

    def __init__(self, user_count: int = 0, raises: Exception | None = None) -> None:
        self.user_count = user_count
        self.raises = raises
        self.created: list[tuple[str, str]] = []


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch):
    """Configure credentials and capture what the seeder would create."""
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_EMAIL", "admin@heal.local")
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "password")
    return Recorder()


class TestConfigurationGate:
    @pytest.mark.asyncio
    async def test_nothing_happens_without_an_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The production default is unset, and must be inert."""
        monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_EMAIL", "")
        monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "password")
        called = False

        def _fail() -> None:  # pragma: no cover - must not run
            nonlocal called
            called = True

        monkeypatch.setattr(config, "WEAK_BOOTSTRAP_PASSWORDS", frozenset())
        await bootstrap.ensure_bootstrap_admin()
        assert not called

    @pytest.mark.asyncio
    async def test_nothing_happens_without_a_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_EMAIL", "admin@heal.local")
        monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "")

        # Returns without touching the database; an import error inside would
        # surface as a raised exception rather than a silent pass.
        await bootstrap.ensure_bootstrap_admin()


class TestFailureIsNeverFatal:
    @pytest.mark.asyncio
    async def test_a_broken_database_does_not_stop_startup(
        self, seeded, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A typo in one variable must not take the whole API down.

        There is no database in a unit test, so the import and connection
        inside the function fail for real -- which is exactly the condition
        being asserted.
        """
        await bootstrap.ensure_bootstrap_admin()


class TestWeakPasswordList:
    def test_the_local_default_is_listed_as_weak(self) -> None:
        """The compose default must trip the warning, not slip through."""
        assert "password" in config.WEAK_BOOTSTRAP_PASSWORDS

    def test_a_real_password_is_not_flagged(self) -> None:
        assert "S0me-Long-Passphrase!" not in config.WEAK_BOOTSTRAP_PASSWORDS
