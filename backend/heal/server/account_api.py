"""Changing your own password.

Kept apart from users_api because it is not an admin power: any signed-in
account may change its own password, and only its own. The case it exists for
is the bootstrap administrator, whose first password sat in an env file.

A change ends every other session of the account, so whoever knew the old
password keeps nothing; the browser that made the change stays signed in.
"""
from typing import cast

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi_users.password import PasswordHelper
from pydantic import BaseModel
from sqlalchemy import CursorResult
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from heal import config
from heal.logger import get_logger
from heal_app.auth.users import cookie_transport
from heal_app.auth.users import current_user
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
    user: User | None = Depends(current_user),
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
