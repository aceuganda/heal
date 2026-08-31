from collections.abc import AsyncGenerator
from typing import Any
from typing import Dict

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.models import UP
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from heal_app.auth.schemas import UserRole
from heal_app.db.engine import get_async_session
from heal_app.db.engine import get_sqlalchemy_async_engine
from heal_app.db.models import AccessToken
from heal_app.db.models import OAuthAccount
from heal_app.db.models import User


async def get_user_count() -> int:
    async with AsyncSession(get_sqlalchemy_async_engine()) as asession:
        stmt = select(func.count(User.id))
        result = await asession.execute(stmt)
        user_count = result.scalar()
        if user_count is None:
            raise RuntimeError("Was not able to fetch the user count.")
        return user_count


# Need to override this because FastAPI Users doesn't give flexibility for backend field creation logic in OAuth flow
class SQLAlchemyUserAdminDB(SQLAlchemyUserDatabase):
    async def create(self, create_dict: Dict[str, Any]) -> UP:
        # Mirrors UserManager.create: the first account bootstraps the
        # deployment as SUPER_ADMIN, everyone after starts at MEMBER. This
        # layer is what the OAuth flow goes through, so the rule has to hold
        # in both places or the two sign-up paths disagree.
        user_count = await get_user_count()
        if user_count == 0:
            create_dict["role"] = UserRole.SUPER_ADMIN
        else:
            create_dict["role"] = UserRole.MEMBER
        return await super().create(create_dict)


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserAdminDB, None]:
    yield SQLAlchemyUserAdminDB(session, User, OAuthAccount)  # type: ignore


async def get_access_token_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase, None]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)  # type: ignore
