import datetime
import uuid

from fastapi_users import schemas
from pydantic import model_validator

from heal.accounts.profile import profile_problem

# The role policy lives in `roles.py` so it can be imported without pulling in
# fastapi-users. Re-exported here because most of the app has always imported
# UserRole from this module.
from heal_app.auth.roles import ASSIGNABLE_ROLES
from heal_app.auth.roles import PRIVILEGED_ROLE
from heal_app.auth.roles import role_at_least
from heal_app.auth.roles import UserRole

# Stands in for a missing date so the shared check reports it as invalid.
_NO_DATE = datetime.date(1, 1, 1)

__all__ = [
    "ASSIGNABLE_ROLES",
    "PRIVILEGED_ROLE",
    "role_at_least",
    "UserRole",
    "UserRead",
    "UserCreate",
    "UserUpdate",
]


class UserRead(schemas.BaseUser[uuid.UUID]):
    role: UserRole
    # Profile and the admin-side access state; defaults keep fastapi-users'
    # own routers working when they build this from a fresh row.
    organisation: str | None = None
    date_of_birth: datetime.date | None = None
    sex: str | None = None
    admin_verified_at: datetime.datetime | None = None
    chat_blocked: bool = False


class UserCreate(schemas.BaseUserCreate):
    role: UserRole = UserRole.MEMBER
    # Sign-up collects the profile up front. Optional so the bootstrap admin
    # and admin-created accounts can still be made without one.
    organisation: str | None = None
    date_of_birth: datetime.date | None = None
    sex: str | None = None

    @model_validator(mode="after")
    def _profile_is_complete(self) -> "UserCreate":
        # All or nothing: a half profile would look filled in while still
        # failing the access check on the first chat.
        given = (self.organisation, self.date_of_birth, self.sex)
        if all(value is None for value in given):
            return self
        problem = profile_problem(
            self.organisation or "", self.date_of_birth or _NO_DATE, self.sex or ""
        )
        if problem:
            raise ValueError(problem)
        self.organisation = (self.organisation or "").strip()
        return self


class UserUpdate(schemas.BaseUserUpdate):
    role: UserRole
