"""Seeding the first administrator.

With authentication on, a fresh database is a locked door: nobody can log in,
and creating an account requires being logged in as an admin. This seeds one
account to break that circle, then never runs again.

Three properties keep it from becoming a back door:

  * it only acts when the user table is EMPTY, so it cannot overwrite a real
    account, re-create a deleted one, or reset a forgotten password;
  * the credentials come from the environment, never from source;
  * with the variables unset -- the production default -- it does nothing.

The seeded account becomes SUPER_ADMIN through the ordinary "first account
bootstraps the deployment" rule in UserManager.create, not through a special
case here.
"""
from heal import config
from heal.logger import get_logger

logger = get_logger(__name__)


async def ensure_bootstrap_admin() -> None:
    """Create the first administrator if the deployment has no users at all.

    Never raises: a failure here must not stop the API from starting, or a
    typo in one environment variable takes the whole service down.
    """
    email = config.BOOTSTRAP_ADMIN_EMAIL
    password = config.BOOTSTRAP_ADMIN_PASSWORD

    if not email or not password:
        logger.info(
            "No bootstrap administrator configured; set "
            "HEAL_BOOTSTRAP_ADMIN_EMAIL and HEAL_BOOTSTRAP_ADMIN_PASSWORD to "
            "seed one into an empty database"
        )
        return

    try:
        from sqlalchemy.ext.asyncio import AsyncSession

        from heal_app.auth.schemas import UserCreate
        from heal_app.auth.users import UserManager
        from heal_app.db.auth import get_user_count
        from heal_app.db.auth import SQLAlchemyUserAdminDB
        from heal_app.db.engine import get_sqlalchemy_async_engine
        from heal_app.db.models import OAuthAccount
        from heal_app.db.models import User

        if await get_user_count() > 0:
            logger.info("Users already exist; skipping bootstrap administrator")
            return

        if password in config.WEAK_BOOTSTRAP_PASSWORDS:
            logger.warning(
                "Bootstrap administrator %s is being created with a well-known "
                "password. This is fine for local development and must NEVER "
                "be used in a deployment -- change it at first login.",
                email,
            )

        # expire_on_commit=False, matching get_async_session(). With the
        # default, committing expires every attribute, and the first thing
        # fastapi-users does next is `on_after_register`, which reads user.id
        # -- a synchronous attribute read that triggers async IO and raises
        # MissingGreenlet *after* the row has already been written.
        async with AsyncSession(
            get_sqlalchemy_async_engine(), expire_on_commit=False
        ) as asession:
            user_db = SQLAlchemyUserAdminDB(asession, User, OAuthAccount)
            manager = UserManager(user_db)
            # Role is not passed: create() assigns SUPER_ADMIN because this is
            # the first account, which is exactly the rule we want applied.
            created = await manager.create(UserCreate(email=email, password=password))
            # Read inside the block. The commit inside create() expires the
            # instance, so touching it after the session closes triggers a
            # refresh -- async IO from a sync context, which raises
            # MissingGreenlet long after the row was already written.
            created_email = created.email
            created_role = created.role.value

        logger.info(
            "Bootstrap administrator created: %s (%s)", created_email, created_role
        )
    except Exception as exc:  # noqa: BLE001 -- never block startup
        # Deliberately does not claim the account was not created: the failure
        # can happen after the row is committed, and a log line insisting
        # otherwise sends whoever reads it looking in the wrong place.
        logger.error(
            "Bootstrap administrator did not complete (%s: %s). The API is "
            "starting anyway -- check the user table before assuming it is "
            "missing.",
            type(exc).__name__,
            exc,
            # With the traceback suppressed, a failure here is a one-line
            # mystery in a container log and the cause has to be guessed.
            exc_info=True,
        )
