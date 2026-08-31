import os
import smtplib
import uuid
from collections.abc import AsyncGenerator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from typing import Tuple

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi_users import BaseUserManager
from fastapi_users import FastAPIUsers
from fastapi_users import models
from fastapi_users import schemas
from fastapi_users import UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend
from fastapi_users.authentication import CookieTransport
from fastapi_users.authentication import Strategy
from fastapi_users.authentication.strategy.db import AccessTokenDatabase
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.openapi import OpenAPIResponseType
from sqlalchemy.orm import Session

from heal_app.auth.schemas import PRIVILEGED_ROLE
from heal_app.auth.schemas import role_at_least
from heal_app.auth.schemas import UserCreate
from heal_app.auth.schemas import UserRole
from heal_app.configs.app_configs import AUTH_TYPE
from heal_app.configs.app_configs import DISABLE_AUTH
from heal_app.configs.app_configs import EMAIL_FROM
from heal_app.configs.app_configs import REQUIRE_EMAIL_VERIFICATION
from heal_app.configs.app_configs import SECRET
from heal_app.configs.app_configs import SESSION_EXPIRE_TIME_SECONDS
from heal_app.configs.app_configs import SMTP_PASS
from heal_app.configs.app_configs import SMTP_PORT
from heal_app.configs.app_configs import SMTP_SERVER
from heal_app.configs.app_configs import SMTP_USER
from heal_app.configs.app_configs import VALID_EMAIL_DOMAINS
from heal_app.configs.app_configs import WEB_DOMAIN
from heal_app.configs.constants import AuthType
from heal_app.db.auth import get_access_token_db
from heal_app.db.auth import get_user_count
from heal_app.db.auth import get_user_db
from heal_app.db.engine import get_session
from heal_app.db.models import AccessToken
from heal_app.db.models import User
from heal_app.utils.logger import setup_logger
from heal_app.utils.telemetry import optional_telemetry
from heal_app.utils.telemetry import RecordType
from heal_app.utils.variable_functionality import fetch_versioned_implementation


logger = setup_logger()

USER_WHITELIST_FILE = "/home/danswer_whitelist.txt"
_user_whitelist: list[str] | None = None


def verify_auth_setting() -> None:
    if AUTH_TYPE not in [AuthType.DISABLED, AuthType.BASIC, AuthType.GOOGLE_OAUTH]:
        raise ValueError(
            "User must choose a valid user authentication method: "
            "disabled, basic, or google_oauth"
        )
    logger.info(f"Using Auth Type: {AUTH_TYPE.value}")


def user_needs_to_be_verified() -> bool:
    # all other auth types besides basic should require users to be
    # verified
    return AUTH_TYPE != AuthType.BASIC or REQUIRE_EMAIL_VERIFICATION


def get_user_whitelist() -> list[str]:
    global _user_whitelist
    if _user_whitelist is None:
        if os.path.exists(USER_WHITELIST_FILE):
            with open(USER_WHITELIST_FILE, "r") as file:
                _user_whitelist = [line.strip() for line in file]
        else:
            _user_whitelist = []

    return _user_whitelist


def verify_email_in_whitelist(email: str) -> None:
    whitelist = get_user_whitelist()
    if (whitelist and email not in whitelist) or not email:
        raise PermissionError("User not on allowed user whitelist")


def verify_email_domain(email: str) -> None:
    if VALID_EMAIL_DOMAINS:
        if email.count("@") != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is not valid",
            )
        domain = email.split("@")[-1]
        if domain not in VALID_EMAIL_DOMAINS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email domain is not valid",
            )


def send_user_verification_email(
    user_email: str,
    token: str,
    mail_from: str = EMAIL_FROM,
) -> None:
    msg = MIMEMultipart()
    msg["Subject"] = "Danswer Email Verification"
    msg["To"] = user_email
    if mail_from:
        msg["From"] = mail_from

    link = f"{WEB_DOMAIN}/auth/verify-email?token={token}"

    body = MIMEText(f"Click the following link to verify your email address: {link}")
    msg.attach(body)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.starttls()
        # If credentials fails with gmail, check (You need an app password, not just the basic email password)
        # https://support.google.com/accounts/answer/185833?sjid=8512343437447396151-NA
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def create(
        self,
        user_create: schemas.UC | UserCreate,
        safe: bool = False,
        request: Optional[Request] = None,
    ) -> models.UP:
        verify_email_in_whitelist(user_create.email)
        verify_email_domain(user_create.email)
        if hasattr(user_create, "role"):
            # Self-registration never chooses its own authority. The first
            # account bootstraps the deployment and gets SUPER_ADMIN -- someone
            # has to be able to set the provider key and appoint admins;
            # everyone after starts at MEMBER and is promoted deliberately.
            #
            # An admin creating a user with a chosen role therefore sets it
            # after this call -- see heal/server/users_api.py.
            user_count = await get_user_count()
            if user_count == 0:
                user_create.role = UserRole.SUPER_ADMIN
            else:
                user_create.role = UserRole.MEMBER
        return await super().create(user_create, safe=safe, request=request)  # type: ignore

    async def oauth_callback(
        self: "BaseUserManager[models.UOAP, models.ID]",
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> models.UOAP:
        verify_email_in_whitelist(account_email)
        verify_email_domain(account_email)

        return await super().oauth_callback(  # type: ignore
            oauth_name=oauth_name,
            access_token=access_token,
            account_id=account_id,
            account_email=account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
            request=request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        logger.info(f"User {user.id} has registered.")
        optional_telemetry(record_type=RecordType.SIGN_UP, data={"user": "create"})

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        logger.info(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        verify_email_domain(user.email)

        logger.info(
            f"Verification requested for user {user.id}. Verification token: {token}"
        )

        send_user_verification_email(user.email, token)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


cookie_transport = CookieTransport(cookie_max_age=SESSION_EXPIRE_TIME_SECONDS)


def get_database_strategy(
    access_token_db: AccessTokenDatabase[AccessToken] = Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(
        access_token_db, lifetime_seconds=SESSION_EXPIRE_TIME_SECONDS  # type: ignore
    )


auth_backend = AuthenticationBackend(
    name="database",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)


class FastAPIUserWithLogoutRouter(FastAPIUsers[models.UP, models.ID]):
    def get_logout_router(
        self,
        backend: AuthenticationBackend,
        requires_verification: bool = REQUIRE_EMAIL_VERIFICATION,
    ) -> APIRouter:
        """
        Provide a router for logout only for OAuth/OIDC Flows.
        This way the login router does not need to be included
        """
        router = APIRouter()
        get_current_user_token = self.authenticator.current_user_token(
            active=True, verified=requires_verification
        )
        logout_responses: OpenAPIResponseType = {
            **{
                status.HTTP_401_UNAUTHORIZED: {
                    "description": "Missing token or inactive user."
                }
            },
            **backend.transport.get_openapi_logout_responses_success(),
        }

        @router.post(
            "/logout", name=f"auth:{backend.name}.logout", responses=logout_responses
        )
        async def logout(
            user_token: Tuple[models.UP, str] = Depends(get_current_user_token),
            strategy: Strategy[models.UP, models.ID] = Depends(backend.get_strategy),
        ) -> Response:
            user, token = user_token
            return await backend.logout(strategy, user, token)

        return router


fastapi_users = FastAPIUserWithLogoutRouter[User, uuid.UUID](
    get_user_manager, [auth_backend]
)


# NOTE: verified=REQUIRE_EMAIL_VERIFICATION is not used here since we
# take care of that in `double_check_user` ourself. This is needed, since
# we want the /me endpoint to still return a user even if they are not
# yet verified, so that the frontend knows they exist
optional_valid_user = fastapi_users.current_user(active=True, optional=True)


async def double_check_user(
    request: Request,
    user: User | None,
    db_session: Session,
    optional: bool = DISABLE_AUTH,
) -> User | None:
    if optional:
        return None

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. User is not authenticated.",
        )

    if user_needs_to_be_verified() and not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. User is not verified.",
        )

    return user


async def current_user(
    request: Request,
    user: User | None = Depends(optional_valid_user),
    db_session: Session = Depends(get_session),
) -> User | None:
    double_check_user = fetch_versioned_implementation(
        "heal_app.auth.users", "double_check_user"
    )
    user = await double_check_user(request, user, db_session)
    return user


async def current_admin_user(user: User | None = Depends(current_user)) -> User | None:
    """Admin surface: the source library, chat sessions, viewing users.

    A super admin outranks an admin, so the check is "at least ADMIN" rather
    than "is ADMIN" -- an equality test here would lock super admins out of
    every screen they are meant to own.
    """
    if DISABLE_AUTH:
        return None

    if not user or not role_at_least(getattr(user, "role", None), UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. User is not an admin.",
        )
    return user


async def current_super_admin_user(
    user: User | None = Depends(current_user),
) -> User | None:
    """Provider API keys, creating users and changing roles.

    Separated from `current_admin_user` because these three are the actions
    that can hand away control of the deployment or spend money on it. What the
    gate currently demands is `PRIVILEGED_ROLE`, which today admits an ADMIN as
    well -- the separation exists in the data now so that tightening it later
    is a one-line change rather than a re-audit of every route.
    """
    if DISABLE_AUTH:
        return None

    if not user or not role_at_least(getattr(user, "role", None), PRIVILEGED_ROLE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access denied. This action requires at least the "
                f"{PRIVILEGED_ROLE.value} role."
            ),
        )
    return user
