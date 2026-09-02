"""Generation tuning as a value, not as global state.

The sibling of `heal/knowledge/settings.py`, and for the same reason: an admin
comparing two temperatures must not change what every concurrent conversation
is being told. `GenerationSettings()` with no arguments reads the deployment's
own defaults, so the chat path passes nothing and behaves as it always did;
`resolve()` builds one from client overrides and reports what it did with them.

"The deployment's own defaults" means `heal.llm.defaults.effective()`: the
environment, with any knob an admin has saved from the playground applied over
it. Read there rather than from `heal.config` directly, so that a saved
temperature reaches the live chat path and not only the screen that set it.

These are the knobs that decide how an answer *reads* rather than what it is
allowed to say. The retrieval floor decides whether a dose may be quoted at
all; temperature only decides how it is worded. They are tuned on the same
screen because an admin judges them from the same output, but they are not the
same kind of setting and the UI should not imply they are.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from typing import Any

from heal.llm import defaults


def _default(name: str) -> Any:
    """One knob's deployment default, saved value first, environment behind it."""
    return defaults.effective()[name]


@dataclass(frozen=True)
class Verbosity:
    """One answer length, as an instruction and as a ceiling.

    The instruction is the part that matters. A token cap does not make a model
    concise, it makes it stop -- and a clinical answer cut off part-way through
    a dose is worse than a long one. So the level ASKS for the length, and the
    budget only stops a "detailed" answer from running away.
    """

    name: str
    label: str
    # Shown under the control, so an admin picks a level by what it does.
    hint: str
    instruction: str
    # Tokens this level is allowed. The applied cap is the smaller of this and
    # the deployment's `max_output_tokens`, which stays the hard ceiling.
    budget: int


VERBOSITY_LEVELS: dict[str, Verbosity] = {
    "brief": Verbosity(
        name="brief",
        label="Brief",
        hint="A few lines. For a health worker reading on a phone with a patient "
        "in front of them.",
        instruction=(
            "Keep this answer short: at most three sentences, or five bullet "
            "points if the answer is genuinely a list. Give the drug, the dose, "
            "the route and the frequency and stop. Do not restate the question, "
            "do not add background that was not asked for, and never drop a "
            "safety warning or a citation to save space."
        ),
        budget=512,
    ),
    "standard": Verbosity(
        name="standard",
        label="Standard",
        hint="The default. Answers at whatever length the question needs.",
        # Deliberately empty. The safety instruction already sets the register,
        # and a second paragraph telling the model to be "clear and helpful"
        # spends context to say nothing.
        instruction="",
        budget=2048,
    ),
    "detailed": Verbosity(
        name="detailed",
        label="Detailed",
        hint="Answer first, then caveats, monitoring and when to refer. For "
        "review and training rather than the point of care.",
        instruction=(
            "Give the direct answer first, in its own short paragraph, then the "
            "supporting detail: relevant contraindications, interactions, "
            "monitoring, and when to refer. Keep it scannable with short "
            "paragraphs or bullets. Do not pad -- if there is nothing further "
            "worth saying, stop."
        ),
        budget=4096,
    ),
}

DEFAULT_VERBOSITY = "standard"


def verbosity(name: str) -> Verbosity:
    """A level by name, falling back to the standard one.

    Never raises. An unrecognised level reaching here means a stale saved value
    or a hand-edited environment variable, and answering at standard length is
    a better outcome than a failed clinical question.
    """
    return VERBOSITY_LEVELS.get(name, VERBOSITY_LEVELS[DEFAULT_VERBOSITY])


@dataclass(frozen=True)
class GenerationSettings:
    """The knobs one generation runs under."""

    temperature: float = field(default_factory=lambda: _default("temperature"))
    max_output_tokens: int = field(
        default_factory=lambda: _default("max_output_tokens")
    )
    top_p: float = field(default_factory=lambda: _default("top_p"))
    verbosity: str = field(default_factory=lambda: _default("verbosity"))

    @property
    def level(self) -> Verbosity:
        """The verbosity level this generation runs at."""
        return verbosity(self.verbosity)

    @property
    def token_cap(self) -> int:
        """Tokens the model may actually produce.

        The smaller of the level's budget and the configured cap. The cap is a
        ceiling the level cannot raise -- an admin who set 512 to control cost
        did not agree to 4096 by also choosing "detailed" -- and the level can
        lower it, so "brief" does not leave a runaway generation room to run.
        """
        return min(self.max_output_tokens, self.level.budget)

    @property
    def instruction(self) -> str:
        """The length instruction to put in the prompt. Empty at standard."""
        return self.level.instruction


# Inclusive bounds. Temperature stops at 1.0 rather than the 2.0 some providers
# allow: above 1.0 a model paraphrases numbers, and this one quotes doses.
BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 1.0),
    "max_output_tokens": (64, 4096),
    "top_p": (0.0, 1.0),
}

# The environment variable each knob defaults from. The playground shows this
# so an admin can see which variable a saved value is standing in front of --
# and so a value can be made permanent in the deployment's own environment
# rather than living only in the database.
ENV_VARS: dict[str, str] = {
    "temperature": "HEAL_TEMPERATURE",
    "max_output_tokens": "HEAL_MAX_OUTPUT_TOKENS",
    "top_p": "HEAL_TOP_P",
    "verbosity": "HEAL_VERBOSITY",
}


@dataclass(frozen=True)
class SettingUsed:
    """One knob, as it was actually applied, with its provenance."""

    name: str
    value: float | int | str
    default: float | int | str
    overridden: bool
    clamped: bool = False
    requested: float | int | str | None = None


def _clamp(name: str, value: float) -> tuple[float, bool]:
    low, high = BOUNDS[name]
    bounded = max(low, min(high, value))
    return bounded, bounded != value


def resolve(
    overrides: Mapping[str, Any] | None = None,
) -> tuple[GenerationSettings, list[SettingUsed]]:
    """Build one request's generation settings from optional overrides.

    Out-of-range values are clamped rather than rejected, matching the
    retrieval side: a slider dragged to its end is a legitimate request, and
    the honest answer is the value that was used. An unknown verbosity level is
    the one exception -- there is no nearest valid value to clamp a bad name
    to, so it is reported as clamped back to the deployment's own level.
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    deployment = GenerationSettings()

    values: dict[str, Any] = {}
    used: list[SettingUsed] = []
    for spec in fields(GenerationSettings):
        name = spec.name
        default = getattr(deployment, name)
        if name not in overrides:
            values[name] = default
            used.append(
                SettingUsed(name=name, value=default, default=default, overridden=False)
            )
            continue

        requested = overrides[name]
        if name == "verbosity":
            known = str(requested) in VERBOSITY_LEVELS
            value: Any = str(requested) if known else default
            was_clamped = not known
        else:
            bounded, was_clamped = _clamp(name, float(requested))
            value = int(bounded) if isinstance(default, int) else bounded
        values[name] = value
        used.append(
            SettingUsed(
                name=name,
                value=value,
                default=default,
                overridden=True,
                clamped=was_clamped,
                requested=requested,
            )
        )

    return GenerationSettings(**values), used
