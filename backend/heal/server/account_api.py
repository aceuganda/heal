"""Your own account: profile, email verification and password.

Kept apart from users_api because none of it is an admin power: any signed-in
account may change its own details, and only its own.

Every route here uses `current_account_user`, which skips the access policy.
A person the policy blocks for being unverified must still be able to reach
these, or nothing they could do would ever lift the block.

The password change exists first for the bootstrap administrator, whose first
password sat in an env file.

A change ends every other session of the account, so whoever knew the old
password keeps nothing; the browser that made the change stays signed in.
"""
import datetime
import smtplib
from typing import cast

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi_users import exceptions as fastapi_users_exceptions
from fastapi_users.password import PasswordHelper
from pydantic import BaseModel
from sqlalchemy import CursorResult
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from heal import config
from heal.accounts.access import blocked_reason
from heal.accounts.profile import profile_problem
from heal.accounts.profile import SEX_OPTIONS
from heal.logger import get_logger
from heal_app.auth.users import cookie_transport
from heal_app.auth.users import current_account_user
from heal_app.auth.users import EmailNotConfigured
from heal_app.auth.users import get_user_manager
from heal_app.auth.users import UserManager
from heal_app.db.engine import get_sqlalchemy_async_engine
from heal_app.db.models import AccessToken
from heal_app.db.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/manage/me")

MIN_PASSWORD_LENGTH = 8

_password_helper = PasswordHelper()


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


def password_problem(current: str, new: str, email: str) -> str | None:
    """Why `new` is not acceptable, or None. Mirrored in the admin page's lib."""
    if len(new) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if new == current:
        return "The new password must be different from the current one."
    if new.lower() in config.WEAK_BOOTSTRAP_PASSWORDS or new.lower() == email.lower():
        return "That password is too easy to guess."
    return None


def _open_session() -> AsyncSession:
    return AsyncSession(get_sqlalchemy_async_engine(), expire_on_commit=False)


@router.post("/password")
async def change_own_password(
    body: PasswordChangeRequest,
    request: Request,
    user: User | None = Depends(current_account_user),
) -> dict[str, int]:
    if user is None:
        # Only with auth disabled: there is no account to change.
        raise HTTPException(status_code=403, detail="Sign in to change a password.")
    user_id = user.id

    async with _open_session() as asession:
        row = await asession.get(User, user_id)
        if row is None:  # pragma: no cover - the session just resolved it
            raise HTTPException(status_code=404, detail="User not found")

        verified, _ = _password_helper.verify_and_update(
            body.current_password, row.hashed_password
        )
        if not verified:
            raise HTTPException(
                status_code=400, detail="The current password is not correct."
            )
        problem = password_problem(body.current_password, body.new_password, row.email)
        if problem:
            raise HTTPException(status_code=422, detail=problem)

        email = row.email
        row.hashed_password = _password_helper.hash(body.new_password)
        asession.add(row)

        # Table columns: the fastapi-users mixin leaves the ORM attributes untyped.
        tokens = AccessToken.__table__.c
        ended = delete(AccessToken).where(tokens.user_id == user_id)
        keep = request.cookies.get(cookie_transport.cookie_name)
        if keep:
            ended = ended.where(tokens.token != keep)
        result = cast(CursorResult, await asession.execute(ended))
        await asession.commit()

    signed_out = int(result.rowcount or 0)
    logger.info("Password changed for %s; ended %d other session(s)", email, signed_out)
    return {"signed_out_sessions": signed_out}


class ProfileView(BaseModel):
    email: str
    organisation: str | None
    date_of_birth: datetime.date | None
    sex: str | None
    sex_options: dict[str, str]
    # Level one: the person clicked the emailed link.
    email_verified: bool
    # Level two: an admin vouched for the account.
    admin_verified: bool
    admin_verified_at: datetime.datetime | None
    chat_blocked: bool
    # Why the access policy refuses this account right now, or null.
    access_blocked_reason: str | None


class ProfileUpdate(BaseModel):
    organisation: str
    date_of_birth: datetime.date
    sex: str


def _view(user: User) -> ProfileView:
    return ProfileView(
        email=user.email,
        organisation=user.organisation,
        date_of_birth=user.date_of_birth,
        sex=user.sex,
        sex_options=SEX_OPTIONS,
        email_verified=bool(user.is_verified),
        admin_verified=user.admin_verified_at is not None,
        admin_verified_at=user.admin_verified_at,
        chat_blocked=bool(user.chat_blocked),
        access_blocked_reason=blocked_reason(user),
    )


def _signed_in(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=403, detail="Sign in to manage an account.")
    return user


@router.get("/profile")
def get_profile(user: User | None = Depends(current_account_user)) -> ProfileView:
    return _view(_signed_in(user))


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: User | None = Depends(current_account_user),
) -> ProfileView:
    user_id = _signed_in(user).id
    problem = profile_problem(body.organisation, body.date_of_birth, body.sex)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    async with _open_session() as asession:
        row = await asession.get(User, user_id)
        if row is None:  # pragma: no cover - the session just resolved it
            raise HTTPException(status_code=404, detail="User not found")
        row.organisation = body.organisation.strip()
        row.date_of_birth = body.date_of_birth
        row.sex = body.sex
        asession.add(row)
        await asession.commit()
        return _view(row)


@router.post("/request-verification")
async def request_verification(
    request: Request,
    user: User | None = Depends(current_account_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> dict[str, str]:
    """Email this account a verification link.

    Wraps fastapi-users' own flow so that the two ways it fails in practice --
    no mail server configured, or the mail server refusing -- come back as a
    sentence the screen can show rather than a bare 500.
    """
    account = _signed_in(user)
    if account.is_verified:
        return {"status": "already_verified"}
    try:
        await user_manager.request_verify(account, request)
    except fastapi_users_exceptions.UserAlreadyVerified:
        return {"status": "already_verified"}
    except EmailNotConfigured as exc:
        logger.warning("Verification email not sent: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Email is not set up on this deployment yet, so no "
            "verification email can be sent. Ask an administrator to verify "
            "your email instead.",
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Verification email failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The verification email could not be sent just now. "
            "Please try again in a few minutes.",
        ) from exc
    return {"status": "sent"}
