"""The deployment's generation defaults: the environment, as an admin amended it.

`heal/config.py` reads every knob from the environment once at import. That is
right for a deployment and wrong for an operator: changing a temperature meant
editing a compose file and restarting, and an admin who found a better value on
the playground had no way to keep it.

So there are two layers, and only two:

  * The environment is the DEFAULT. It is what a fresh install runs on, what a
    re-pointed deployment runs on, and what everything falls back to.
  * The `model_settings` row is the OVERRIDE. It holds only the knobs somebody
    deliberately changed; a null column means "still following the environment".

`effective()` composes them and is the only thing anything else should read.
Nothing in this module writes to `heal.config`: a module-level mutation would
change the behaviour of every conversation running at that moment with nothing
in the audit trail to say why, which is exactly the failure the settings-as-a-
value design elsewhere in `heal/llm` and `heal/knowledge` forecloses.

**A failure here is never a failure of the chat path.** A database that cannot
be reached, or a table that has not been migrated yet, means the deployment
runs on its environment -- which is the state it was in before this existed.
The alternative, an unanswered clinical question because a settings lookup
timed out, is not a trade worth making.
"""
import time
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from heal import config
from heal.logger import get_logger

logger = get_logger(__name__)

# Every knob this table is allowed to hold, in the order a screen shows them.
# A name not in here is rejected on write rather than silently dropped: a save
# that reports success and stores nothing is worse than a 422.
FIELDS: tuple[str, ...] = (
    "temperature",
    "max_output_tokens",
    "top_p",
    "verbosity",
    "chat_model",
    "classifier_model",
)

# The single row's id. There is one answer to "what does this deployment run
# at", and the check constraint on the table enforces that there can only be.
ROW_ID = 1

# How long a cached read is trusted, in seconds.
#
# This is read on every generation, so it cannot be a query per message; and it
# is written from a screen whose user expects the next message to reflect the
# change, so it cannot be cached for the life of the process. A save
# invalidates the cache in the worker that handled it immediately, so the TTL
# only bounds how long the OTHER API workers keep serving the old value.
CACHE_TTL_SECONDS = 15.0

_cache: dict[str, Any] | None = None
_cached_at: float = 0.0


def env_defaults() -> dict[str, Any]:
    """What the environment alone says. Read per call, not at import.

    Per call because tests monkeypatch `config` after this module is imported,
    and because reading a module constant into a dict at import would make the
    two disagree the first time anything did.
    """
    return {
        "temperature": config.TEMPERATURE,
        "max_output_tokens": config.MAX_OUTPUT_TOKENS,
        "top_p": config.TOP_P,
        "verbosity": config.VERBOSITY,
        "chat_model": config.CHAT_MODEL,
        "classifier_model": config.CLASSIFIER_MODEL,
    }


def invalidate() -> None:
    """Forget the cached row. Called after a write, and by tests."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0


def stored(refresh: bool = False) -> dict[str, Any]:
    """The saved overrides: only the knobs somebody actually changed.

    Returns an empty mapping when nothing is saved, when the table has not been
    migrated yet, or when the database cannot be reached -- all three mean the
    same thing to a caller, which is "run on the environment".
    """
    global _cache, _cached_at

    if (
        not refresh
        and _cache is not None
        and time.monotonic() - _cached_at < (CACHE_TTL_SECONDS)
    ):
        return dict(_cache)

    values = _read_row()
    _cache = values
    _cached_at = time.monotonic()
    return dict(values)


def effective() -> dict[str, Any]:
    """The values this deployment actually runs on, env with overrides applied."""
    return {**env_defaults(), **stored()}


def sources() -> dict[str, str]:
    """Where each value came from: "saved" or "environment".

    So a screen can say which of the two an admin is looking at. A value that
    happens to equal the environment's is still reported as saved: somebody
    chose it, and hiding that would make a deliberate decision look like a
    default nobody has reviewed.
    """
    saved = stored()
    return {name: ("saved" if name in saved else "environment") for name in FIELDS}


def _read_row() -> dict[str, Any]:
    """One query for the settings row, returning only its non-null columns."""
    try:
        from sqlalchemy.orm import Session

        from heal_app.db.engine import get_sqlalchemy_engine
        from heal_app.db.models import ModelSettings

        with Session(get_sqlalchemy_engine(), expire_on_commit=False) as session:
            row = session.get(ModelSettings, ROW_ID)
            if row is None:
                return {}
            return {
                name: getattr(row, name)
                for name in FIELDS
                if getattr(row, name) is not None
            }
    except Exception as exc:  # noqa: BLE001 -- the environment is the fallback
        logger.warning(
            "Could not read saved model settings (%s); using the environment",
            type(exc).__name__,
        )
        return {}


def save(values: Mapping[str, Any], actor_id: UUID | None = None) -> dict[str, Any]:
    """Write the named knobs, then return the new effective settings.

    A key present with a value of `None` CLEARS that knob back to the
    environment; a key that is absent is left exactly as it was. The two are
    different operations and the caller has to be able to express both --
    "reset temperature" and "I did not touch temperature" cannot be the same
    request.

    Validation belongs to the caller (see `heal/llm/settings.py` for the bounds
    and `heal/llm/registry.py` for the model ids). This function is the writer,
    not the referee; it refuses only names it does not know, because storing
    one would be a silent no-op.
    """
    unknown = sorted(set(values) - set(FIELDS))
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(unknown)}")

    from sqlalchemy.orm import Session

    from heal_app.db.engine import get_sqlalchemy_engine
    from heal_app.db.models import ModelSettings

    with Session(get_sqlalchemy_engine()) as session:
        row = session.get(ModelSettings, ROW_ID)
        if row is None:
            row = ModelSettings(id=ROW_ID)
            session.add(row)
        for name, value in values.items():
            setattr(row, name, value)
        # Written explicitly rather than left to a server-side onupdate: the
        # screen shows "changed by X at Y", and a timestamp that only moves on
        # some updates would make that line quietly wrong.
        row.updated_at = _now()
        row.updated_by_id = actor_id
        session.commit()

    invalidate()
    return effective()


def _now():  # type: ignore[no-untyped-def]
    from datetime import datetime
    from datetime import timezone

    return datetime.now(timezone.utc)


def last_change() -> tuple[Any, str | None]:
    """When the settings were last saved and by whom, for the screen's byline.

    Returns `(None, None)` when nothing has ever been saved. Never raises: a
    missing byline is a cosmetic loss, not a reason to fail the request.
    """
    try:
        from sqlalchemy.orm import Session

        from heal_app.db.engine import get_sqlalchemy_engine
        from heal_app.db.models import ModelSettings
        from heal_app.db.models import User

        with Session(get_sqlalchemy_engine()) as session:
            row = session.get(ModelSettings, ROW_ID)
            if row is None:
                return None, None
            email = None
            if row.updated_by_id is not None:
                user = session.get(User, row.updated_by_id)
                email = user.email if user else None
            return row.updated_at, email
    except Exception as exc:  # noqa: BLE001 -- a byline is not worth a 500
        logger.warning("Could not read settings byline (%s)", type(exc).__name__)
        return None, None
