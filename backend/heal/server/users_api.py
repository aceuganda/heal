"""Admin API for user accounts.

Two actions live here and nowhere else: creating an account, and changing what
an account is allowed to do. Both are super-admin only, because both are ways
of handing out control of the deployment.

The requested role is applied AFTER `UserManager.create`, not through it. That
method deliberately overrides whatever role it is handed -- self-registration
must never be able to choose its own authority -- so creating an admin is two
steps by design rather than by oversight.

One invariant is enforced here and nowhere else: a deployment always keeps at
least one super admin. Without it, a single careless demotion locks everyone
out of the API keys and of user management, with no in-app way back.
"""
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi_users.exceptions import InvalidPasswordException
from fastapi_users.exceptions import UserAlreadyExists
from pydantic import BaseModel
from pydantic import EmailStr
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heal.logger import get_logger
from heal_app.auth.schemas import ASSIGNABLE_ROLES
from heal_app.auth.schemas import UserCreate
from heal_app.auth.schemas import UserRole
from heal_app.auth.users import current_super_admin_user
from heal_app.auth.users import get_user_manager
from heal_app.auth.users import UserManager
from heal_app.db.engine import get_sqlalchemy_async_engine
from heal_app.db.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/manage/users")


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.MEMBER


class RoleChangeRequest(BaseModel):
    role: UserRole


class UserSummary(BaseModel):
    id: str
    email: str
    role: UserRole
    is_active: bool
    is_verified: bool


def _reject_unassignable(role: UserRole) -> None:
    """BASIC is a legacy stored value, not something a screen may hand out."""
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{role.value}' cannot be assigned. Choose one of: "
                + ", ".join(r.value for r in ASSIGNABLE_ROLES)
            ),
        )


async def _count_super_admins(asession: AsyncSession) -> int:
    result = await asession.execute(
        select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN)
    )
    return int(result.scalar() or 0)


@router.post("")
async def create_user(
    request: CreateUserRequest,
    _: User | None = Depends(current_super_admin_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> UserSummary:
    """Create an account with a chosen role.

    Password rules, hashing and duplicate detection all come from
    `UserManager.create` rather than being re-implemented here.
    """
    _reject_unassignable(request.role)

    try:
        created = await user_manager.create(
            UserCreate(email=request.email, password=request.password)
        )
    except UserAlreadyExists:
        raise HTTPException(
            status_code=409, detail=f"{request.email} already has an account"
        )
    except InvalidPasswordException as exc:
        # 422 with the manager's own reason, so the admin is told what to fix.
        raise HTTPException(status_code=422, detail=str(exc.reason)) from exc

    # Read the row's fields off the instance now, before the second session
    # below touches the same row.
    created_id = created.id
    email = created.email
    is_active = created.is_active
    is_verified = created.is_verified
    assigned_role = created.role

    # create() decided the role for us; apply the one that was actually asked
    # for. The first account is the exception -- it bootstraps as SUPER_ADMIN
    # and is left alone, so a deployment cannot exist without one.
    if assigned_role != UserRole.SUPER_ADMIN and assigned_role != request.role:
        async with AsyncSession(
            get_sqlalchemy_async_engine(), expire_on_commit=False
        ) as asession:
            user = await asession.get(User, created_id)
            if user is None:  # pragma: no cover - created moments ago
                raise HTTPException(status_code=404, detail="User not found")
            user.role = request.role
            asession.add(user)
            await asession.commit()
        assigned_role = request.role

    logger.info("Created user %s with role %s", email, assigned_role.value)
    return UserSummary(
        id=str(created_id),
        email=email,
        role=assigned_role,
        is_active=is_active,
        is_verified=is_verified,
    )


@router.patch("/{user_id}/role")
async def change_user_role(
    user_id: str,
    request: RoleChangeRequest,
    _: User | None = Depends(current_super_admin_user),
) -> dict[str, Any]:
    """Move an account between MEMBER, ADMIN and SUPER_ADMIN.

    Refuses the demotion that would leave the deployment with no super admin.
    """
    _reject_unassignable(request.role)

    try:
        target_id = uuid.UUID(user_id)
    except ValueError:
        # The id comes from the URL, so a malformed one is a bad request rather
        # than a missing user -- and `session.get` on a UUID column would raise
        # a database error instead of returning None.
        raise HTTPException(status_code=422, detail="Not a valid user id")

    async with AsyncSession(get_sqlalchemy_async_engine()) as asession:
        user = await asession.get(User, target_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Read what is needed for the response and the log line BEFORE the
        # commit: committing expires the instance, and the session closes with
        # the block, so touching user.email afterwards raises instead of
        # returning the address.
        email = user.email
        previous = user.role

        if previous == request.role:
            return {"id": user_id, "email": email, "role": request.role.value}

        losing_super_admin = (
            previous == UserRole.SUPER_ADMIN and request.role != UserRole.SUPER_ADMIN
        )
        if losing_super_admin and await _count_super_admins(asession) <= 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This is the only super admin. Promote someone else first, "
                    "otherwise nobody can manage API keys or users."
                ),
            )

        user.role = request.role
        asession.add(user)
        await asession.commit()

    logger.info(
        "Role changed for %s: %s -> %s", email, previous.value, request.role.value
    )
    return {"id": user_id, "email": email, "role": request.role.value}
