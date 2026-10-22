"""Who may use Heal right now: the access policy and the per-account blocks.

Two independent levels of verification exist on every account:

  * email  -- `is_verified`, set when the person clicks the emailed link
  * admin  -- `admin_verified_at`, set when an admin vouches for them

Neither blocks anything on its own. An admin turns blocking on per level in
the `access_policy` row; with no row, or both switches off, every signed-in
account has full access. That is how every deployment starts.

**Admins are never blocked by the policy.** A deployment whose admins could
be locked out by a switch on their own dashboard has no in-app way back.

A failure to read the policy fails OPEN: nobody is blocked. Blocking is a
newly added restriction; an unreachable settings row must not become an
outage for every health worker.
"""
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from heal.logger import get_logger
from heal_app.auth.roles import role_at_least
from heal_app.auth.roles import UserRole

logger = get_logger(__name__)

ROW_ID = 1

# Read on every authenticated request, so cached; a save invalidates this
# worker's copy at once and the TTL bounds the others.
CACHE_TTL_SECONDS = 15.0

EMAIL_UNVERIFIED_MESSAGE = (
    "Verify your email address to use Heal. Open Account settings to send "
    "the verification email."
)
ADMIN_UNVERIFIED_MESSAGE = (
    "Your account is waiting for an administrator to verify it. You can "
    "still update your details in Account settings."
)
CHAT_BLOCKED_MESSAGE = (
    "An administrator has paused chat for your account. Contact your "
    "administrator if you think this is a mistake."
)


@dataclass(frozen=True)
class Policy:
    block_email_unverified: bool = False
    block_admin_unverified: bool = False


_cache: Policy | None = None
_cached_at = 0.0


def invalidate() -> None:
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0


def current_policy(refresh: bool = False) -> Policy:
    global _cache, _cached_at
    if (
        not refresh
        and _cache is not None
        and time.monotonic() - _cached_at < CACHE_TTL_SECONDS
    ):
        return _cache
    policy = _read()
    _cache, _cached_at = policy, time.monotonic()
    return policy


def _read() -> Policy:
    try:
        from sqlalchemy.orm import Session

        from heal_app.db.engine import get_sqlalchemy_engine
        from heal_app.db.models import AccessPolicy

        with Session(get_sqlalchemy_engine()) as session:
            row = session.get(AccessPolicy, ROW_ID)
            if row is None:
                return Policy()
            return Policy(
                block_email_unverified=row.block_email_unverified,
                block_admin_unverified=row.block_admin_unverified,
            )
    except Exception as exc:  # noqa: BLE001 -- fail open, see module docstring
        logger.warning(
            "Could not read the access policy (%s); blocking nobody",
            type(exc).__name__,
        )
        return Policy()


def save(values: dict[str, bool], actor_id: UUID | None) -> Policy:
    """Write the switches that were sent; absent keys are left alone."""
    from datetime import datetime
    from datetime import timezone

    from sqlalchemy.orm import Session

    from heal_app.db.engine import get_sqlalchemy_engine
    from heal_app.db.models import AccessPolicy

    with Session(get_sqlalchemy_engine()) as session:
        row = session.get(AccessPolicy, ROW_ID)
        if row is None:
            row = AccessPolicy(
                id=ROW_ID, block_email_unverified=False, block_admin_unverified=False
            )
            session.add(row)
        for name, value in values.items():
            setattr(row, name, bool(value))
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by_id = actor_id
        session.commit()

    invalidate()
    return current_policy(refresh=True)


def blocked_reason(user: Any, policy: Policy | None = None) -> str | None:
    """The message to refuse this account with, or None if it may proceed.

    `user` is anything with `role`, `is_verified` and `admin_verified_at`, so
    this is testable without the ORM.
    """
    if user is None or role_at_least(getattr(user, "role", None), UserRole.ADMIN):
        return None
    policy = policy or current_policy()
    if policy.block_email_unverified and not getattr(user, "is_verified", False):
        return EMAIL_UNVERIFIED_MESSAGE
    if (
        policy.block_admin_unverified
        and getattr(user, "admin_verified_at", None) is None
    ):
        return ADMIN_UNVERIFIED_MESSAGE
    return None
