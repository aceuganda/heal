import uuid

from fastapi_users import schemas

# The role policy lives in `roles.py` so it can be imported without pulling in
# fastapi-users. Re-exported here because most of the app has always imported
# UserRole from this module.
from heal_app.auth.roles import ASSIGNABLE_ROLES
from heal_app.auth.roles import PRIVILEGED_ROLE
from heal_app.auth.roles import role_at_least
from heal_app.auth.roles import UserRole

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


class UserCreate(schemas.BaseUserCreate):
    role: UserRole = UserRole.MEMBER


class UserUpdate(schemas.BaseUserUpdate):
    role: UserRole
