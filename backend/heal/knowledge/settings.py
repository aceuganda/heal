"""Retrieval tuning as a value, not as global state.

Every constant here also exists in `heal/config.py`, read from the environment
once at import. That is right for a deployment: the live chat path a health
worker uses must behave the same for every concurrent conversation, and the
only way to change it is a restart with a different environment.

It is wrong for an admin who wants to try a different score floor. Writing the
module constant -- even "temporarily", even under a lock -- changes the clinical
behaviour of every conversation running at that moment, with nothing in the
audit trail to say why an answer differed. So the tunables are lifted into a
frozen value that travels as an argument instead:

  * `RetrievalSettings()` with no arguments reads today's config, so the live
    path passes nothing and behaves exactly as it did before this existed.
  * `resolve()` builds one from client-supplied overrides, clamping each into a
    range the pipeline can actually honour, and reports what it did.

The defaults are read at construction, not at import, so a test that
monkeypatches `config.MIN_RETRIEVAL_SCORE` still steers the store.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from typing import Any

from heal import config


@dataclass(frozen=True)
class RetrievalSettings:
    """The knobs one retrieval runs under.

    Field names match the lower-cased config constants they default to, which
    is the same vocabulary `collection_stats()` and the admin UI already use.
    """

    min_retrieval_score: float = field(
        default_factory=lambda: config.MIN_RETRIEVAL_SCORE
    )
    hybrid_alpha: float = field(default_factory=lambda: config.HYBRID_ALPHA)
    hybrid_search: bool = field(default_factory=lambda: config.HYBRID_SEARCH)
    retrieval_top_k: int = field(default_factory=lambda: config.RETRIEVAL_TOP_K)
    context_top_k: int = field(default_factory=lambda: config.CONTEXT_TOP_K)
    max_chunks_per_source: int = field(
        default_factory=lambda: config.MAX_CHUNKS_PER_SOURCE
    )

    @property
    def alpha(self) -> float:
        """Fusion weight actually applied: 1.0 (dense-only) when hybrid is off."""
        return self.hybrid_alpha if self.hybrid_search else 1.0


# Inclusive bounds for every numeric knob. A client is never trusted with
# these: a floor of 50 refuses every question, and a top-k of 100000 asks
# Qdrant for the whole collection on one request.
#
# The upper bounds on the k values are generous rather than tight. They exist
# to stop a typo from becoming an outage, not to express an opinion about what
# a sensible value is -- that is what the eval set is for.
BOUNDS: dict[str, tuple[float, float]] = {
    "min_retrieval_score": (0.0, 1.0),
    "hybrid_alpha": (0.0, 1.0),
    "retrieval_top_k": (1, 200),
    "context_top_k": (1, 50),
    "max_chunks_per_source": (1, 50),
}

# The environment variable each knob is set from, so the playground can say how
# to make a value that worked the default for every chat.
ENV_VARS: dict[str, str] = {
    "min_retrieval_score": "HEAL_MIN_RETRIEVAL_SCORE",
    "hybrid_alpha": "HEAL_HYBRID_ALPHA",
    "hybrid_search": "HEAL_HYBRID_SEARCH",
    "retrieval_top_k": "HEAL_RETRIEVAL_TOP_K",
    "context_top_k": "HEAL_CONTEXT_TOP_K",
    "max_chunks_per_source": "HEAL_MAX_CHUNKS_PER_SOURCE",
}


@dataclass(frozen=True)
class SettingUsed:
    """One knob, as it was actually applied, with its provenance.

    `requested` and `clamped` are carried so a screen can never claim a run
    used the number that was typed when the server pulled it into range.
    """

    name: str
    value: float | int | bool
    default: float | int | bool
    overridden: bool
    clamped: bool = False
    requested: float | int | bool | None = None


def _clamp(name: str, value: float) -> tuple[float, bool]:
    low, high = BOUNDS[name]
    bounded = max(low, min(high, value))
    return bounded, bounded != value


def resolve(
    overrides: Mapping[str, Any] | None = None,
) -> tuple[RetrievalSettings, list[SettingUsed]]:
    """Build one request's settings from optional overrides.

    A `None` override means "leave it alone", which is what lets a caller send
    only the two knobs it changed. Anything out of range is clamped rather than
    rejected: a slider that has been dragged to its end is a legitimate thing
    to ask for, and a 422 there would be a worse answer than the honest "this
    is the value we used".

    Returns the settings and a per-knob record of how each value was arrived
    at, in a fixed order so the screen renders the same way every time.
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    defaults = RetrievalSettings()

    values: dict[str, Any] = {}
    used: list[SettingUsed] = []
    for spec in fields(RetrievalSettings):
        name = spec.name
        default = getattr(defaults, name)
        if name not in overrides:
            values[name] = default
            used.append(
                SettingUsed(name=name, value=default, default=default, overridden=False)
            )
            continue

        requested = overrides[name]
        if name == "hybrid_search":
            value: Any = bool(requested)
            was_clamped = False
        elif isinstance(default, int) and not isinstance(default, bool):
            bounded, was_clamped = _clamp(name, float(requested))
            value = int(bounded)
        else:
            value, was_clamped = _clamp(name, float(requested))

        values[name] = value
        used.append(
            SettingUsed(
                name=name,
                value=value,
                default=default,
                # A value that happens to equal the default is still reported
                # as overridden: the admin set it deliberately, and hiding
                # that would make two different runs look identical.
                overridden=True,
                clamped=was_clamped,
                requested=requested,
            )
        )

    return RetrievalSettings(**values), used
