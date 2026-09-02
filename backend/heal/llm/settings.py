"""Generation tuning as a value, not as global state.

The sibling of `heal/knowledge/settings.py`, and for the same reason: an admin
comparing two temperatures must not change what every concurrent conversation
is being told. `GenerationSettings()` with no arguments reads the deployment's
own constants, so the chat path passes nothing and behaves as it always did;
`resolve()` builds one from client overrides and reports what it did with them.

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

from heal import config


@dataclass(frozen=True)
class GenerationSettings:
    """The knobs one generation runs under."""

    temperature: float = field(default_factory=lambda: config.TEMPERATURE)
    max_output_tokens: int = field(default_factory=lambda: config.MAX_OUTPUT_TOKENS)
    top_p: float = field(default_factory=lambda: config.TOP_P)


# Inclusive bounds. Temperature stops at 1.0 rather than the 2.0 some providers
# allow: above 1.0 a model paraphrases numbers, and this one quotes doses.
BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 1.0),
    "max_output_tokens": (64, 4096),
    "top_p": (0.0, 1.0),
}

# The environment variable each knob is set from, so the playground can tell an
# admin how to make a value they liked permanent. A screen that lets you tune
# something without saying how to keep it is only half a tool.
ENV_VARS: dict[str, str] = {
    "temperature": "HEAL_TEMPERATURE",
    "max_output_tokens": "HEAL_MAX_OUTPUT_TOKENS",
    "top_p": "HEAL_TOP_P",
}


@dataclass(frozen=True)
class SettingUsed:
    """One knob, as it was actually applied, with its provenance."""

    name: str
    value: float | int
    default: float | int
    overridden: bool
    clamped: bool = False
    requested: float | int | None = None


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
    the honest answer is the value that was used.
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    defaults = GenerationSettings()

    values: dict[str, Any] = {}
    used: list[SettingUsed] = []
    for spec in fields(GenerationSettings):
        name = spec.name
        default = getattr(defaults, name)
        if name not in overrides:
            values[name] = default
            used.append(
                SettingUsed(name=name, value=default, default=default, overridden=False)
            )
            continue

        requested = overrides[name]
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
