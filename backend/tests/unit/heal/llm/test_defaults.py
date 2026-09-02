"""The deployment's generation defaults: environment first, saved values over it.

Two properties matter here, and they pull in opposite directions.

The first is that a saved value REACHES THE CHAT PATH. That is the whole point
of the table: an admin who saves a verbosity level has changed what the next
health worker reads, and a setting that only moved the admin screen would be a
lie told by a working-looking feature.

The second is that a failure to read it COSTS NOTHING. A database that is down,
or a table that has not been migrated yet, must leave the deployment running on
its environment -- which is the state it was in before any of this existed. An
unanswered clinical question because a settings lookup timed out is not a trade
worth making.
"""
import pytest

from heal import config
from heal.llm import defaults
from heal.llm.settings import GenerationSettings
from heal.llm.settings import resolve
from heal.llm.settings import VERBOSITY_LEVELS


@pytest.fixture(autouse=True)
def pinned_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the env layer so a test asserts behaviour, not today's deployment."""
    monkeypatch.setattr(config, "TEMPERATURE", 0.0)
    monkeypatch.setattr(config, "MAX_OUTPUT_TOKENS", 1024)
    monkeypatch.setattr(config, "TOP_P", 1.0)
    monkeypatch.setattr(config, "VERBOSITY", "standard")
    monkeypatch.setattr(config, "CHAT_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(config, "CLASSIFIER_MODEL", "gpt-4o-mini")


def saved(monkeypatch: pytest.MonkeyPatch, **values) -> None:
    """Pretend the given knobs are saved in the table."""
    monkeypatch.setattr(defaults, "stored", lambda refresh=False: dict(values))


class TestComposition:
    def test_nothing_saved_is_the_environment(self) -> None:
        assert defaults.effective()["temperature"] == 0.0
        assert defaults.effective()["chat_model"] == "gpt-4o-mini"

    def test_a_saved_value_wins_over_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, temperature=0.4)
        assert defaults.effective()["temperature"] == 0.4

    def test_an_unsaved_knob_still_follows_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The reason every column is nullable rather than the row being a
        # snapshot: saving a temperature must not freeze today's model id.
        saved(monkeypatch, temperature=0.4)
        assert defaults.effective()["chat_model"] == "gpt-4o-mini"

    def test_a_later_environment_change_still_reaches_an_unsaved_knob(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, temperature=0.4)
        monkeypatch.setattr(config, "MAX_OUTPUT_TOKENS", 2048)
        assert defaults.effective()["max_output_tokens"] == 2048

    def test_the_source_of_each_value_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, temperature=0.4)
        sources = defaults.sources()
        assert sources["temperature"] == "saved"
        assert sources["top_p"] == "environment"

    def test_a_saved_value_equal_to_the_environment_is_still_saved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Somebody chose it. Reporting it as a default nobody has reviewed
        # would hide a deliberate decision.
        saved(monkeypatch, temperature=0.0)
        assert defaults.sources()["temperature"] == "saved"


class TestFailureIsNeverFatal:
    """A settings lookup must never be the reason a question goes unanswered."""

    @pytest.fixture
    def unreachable_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from heal_app.db import engine

        def explode(*_args, **_kwargs):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(engine, "get_sqlalchemy_engine", explode)
        defaults.invalidate()

    def test_a_read_that_raises_returns_no_overrides(
        self, unreachable_database
    ) -> None:
        # `_read_row` is the real reader -- the conftest stubs `stored`, one
        # layer above -- so this exercises the guard the chat path depends on.
        assert defaults._read_row() == {}

    def test_the_deployment_then_runs_on_its_environment(
        self, unreachable_database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TEMPERATURE", 0.3)
        # Composed the way `effective()` composes it, but through the real
        # reader rather than the stub.
        composed = {**defaults.env_defaults(), **defaults._read_row()}
        assert composed["temperature"] == 0.3

    def test_a_missing_byline_is_not_an_error(self, unreachable_database) -> None:
        assert defaults.last_change() == (None, None)


class TestGenerationSettingsReadThem:
    def test_a_saved_temperature_reaches_the_settings_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, temperature=0.7)
        assert GenerationSettings().temperature == 0.7

    def test_a_saved_verbosity_reaches_the_prompt_instruction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, verbosity="brief")
        assert "three sentences" in GenerationSettings().instruction

    def test_the_standard_level_adds_nothing_to_the_prompt(self) -> None:
        # Context spent saying "be clear and helpful" is context not spent on
        # an approved passage.
        assert GenerationSettings().instruction == ""


class TestVerbosityAndTheTokenCeiling:
    def test_brief_lowers_the_cap_below_the_configured_ceiling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, verbosity="brief")
        assert GenerationSettings().token_cap == VERBOSITY_LEVELS["brief"].budget

    def test_detailed_cannot_raise_the_cap_above_the_ceiling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An admin who set 1024 to control cost did not agree to 4096 by also
        # choosing "detailed".
        saved(monkeypatch, verbosity="detailed")
        assert GenerationSettings().token_cap == 1024

    def test_an_unknown_level_answers_at_standard_length(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A stale saved value or a hand-edited env var. Answering at standard
        # length beats failing a clinical question over a bad string.
        saved(monkeypatch, verbosity="verbose-ish")
        assert GenerationSettings().level.name == "standard"


class TestPerRunOverrides:
    def test_an_override_does_not_touch_the_saved_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved(monkeypatch, temperature=0.2)
        settings, _ = resolve({"temperature": 0.9})
        assert settings.temperature == 0.9
        assert defaults.effective()["temperature"] == 0.2

    def test_the_default_reported_is_the_saved_one_not_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The screen marks a knob as "changed" against this number, so if it
        # were the environment's an admin would be told a run was non-default
        # when it was exactly what health workers get.
        saved(monkeypatch, temperature=0.2)
        _, used = resolve({"temperature": 0.9})
        entry = next(item for item in used if item.name == "temperature")
        assert entry.default == 0.2

    def test_an_unknown_verbosity_override_is_reported_as_clamped(self) -> None:
        _, used = resolve({"verbosity": "enormous"})
        entry = next(item for item in used if item.name == "verbosity")
        assert entry.clamped
        assert entry.requested == "enormous"
        assert entry.value == "standard"

    def test_a_known_verbosity_override_is_kept(self) -> None:
        settings, used = resolve({"verbosity": "brief"})
        entry = next(item for item in used if item.name == "verbosity")
        assert settings.verbosity == "brief"
        assert entry.overridden and not entry.clamped


class TestWriteGuard:
    def test_an_unknown_setting_is_refused(self) -> None:
        # A save that reports success and stores nothing is worse than a 422.
        with pytest.raises(ValueError, match="min_retrieval_score"):
            defaults.save({"min_retrieval_score": 0.5})
