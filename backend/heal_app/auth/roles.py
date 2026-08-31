"""Who may do what.

Kept apart from `schemas.py` on purpose: that module pulls in fastapi-users,
while this is the policy the whole app authorises against. Isolating it means
the rules can be imported -- and tested -- without the auth stack, and there is
exactly one place to read to find out what a role is allowed to do.
"""
from enum import Enum


class UserRole(str, Enum):
    """The three tiers.

    SUPER_ADMIN  everything: provider API keys, creating users, changing roles
    ADMIN        the approved-source library and chat sessions
    MEMBER       chat only; no admin surface at all

    BASIC is the name MEMBER had before the split. It is kept because an
    unknown value raises LookupError when the row is read, which would lock
    every existing user out during a rollout. Migration a1c4f7d2e9b0 converts
    the rows; treat it as MEMBER everywhere until it can be deleted.
    """

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MEMBER = "member"
    BASIC = "basic"


# Ascending authority. Checks ask "is this role at least X", so a new tier is
# one entry here rather than a new condition at every call site.
_ROLE_RANK: dict[str, int] = {
    UserRole.BASIC.value: 0,
    UserRole.MEMBER.value: 0,
    UserRole.ADMIN.value: 1,
    UserRole.SUPER_ADMIN.value: 2,
}

# Roles an admin screen may actually assign. BASIC is legacy and never offered.
ASSIGNABLE_ROLES = (UserRole.MEMBER, UserRole.ADMIN, UserRole.SUPER_ADMIN)

# What the privileged gate -- API keys, creating users, changing roles --
# actually requires today.
#
# The two tiers are stored and displayed separately, but for now an ADMIN
# carries the same powers as a SUPER_ADMIN, so the pilot is not blocked on
# there being exactly one person who can do anything. Tighten it by setting
# this to UserRole.SUPER_ADMIN: no other line changes, and no call site has to
# be re-audited.
PRIVILEGED_ROLE = UserRole.ADMIN


def role_at_least(role: UserRole | None, minimum: UserRole) -> bool:
    """True if `role` carries at least `minimum`'s authority.

    Always this, never `==`. An equality test against ADMIN silently locks out
    SUPER_ADMIN, which is the failure mode that hurts most: the person with the
    most authority loses access to the screens they own.
    """
    if role is None:
        return False
    return _ROLE_RANK.get(role.value, 0) >= _ROLE_RANK[minimum.value]
