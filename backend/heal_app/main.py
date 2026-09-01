from typing import Any
from typing import cast

import uvicorn
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx_oauth.clients.google import GoogleOAuth2

from heal import config as heal_config
from heal.bootstrap import ensure_bootstrap_admin
from heal.server.api_key import get_danswer_api_key
from heal.knowledge.startup import prepare_knowledge_store_in_background
from heal.server.knowledge_api import router as knowledge_router
from heal.server.reference_api import router as reference_router
from heal.server.users_api import router as users_admin_router
from heal_app import __version__
from heal_app.auth.schemas import UserCreate
from heal_app.auth.schemas import UserRead
from heal_app.auth.schemas import UserUpdate
from heal_app.auth.users import auth_backend
from heal_app.auth.users import fastapi_users
from heal_app.chat.load_yamls import load_chat_yamls
from heal_app.configs.app_configs import APP_API_PREFIX
from heal_app.configs.app_configs import APP_HOST
from heal_app.configs.app_configs import APP_PORT
from heal_app.configs.app_configs import AUTH_TYPE
from heal_app.configs.app_configs import DISABLE_GENERATIVE_AI
from heal_app.configs.app_configs import OAUTH_CLIENT_ID
from heal_app.configs.app_configs import OAUTH_CLIENT_SECRET
from heal_app.configs.app_configs import SECRET
from heal_app.configs.app_configs import WEB_DOMAIN
from heal_app.configs.chat_configs import MULTILINGUAL_QUERY_EXPANSION
from heal_app.configs.constants import AuthType
from heal_app.configs.model_configs import ASYM_PASSAGE_PREFIX
from heal_app.configs.model_configs import ASYM_QUERY_PREFIX
from heal_app.configs.model_configs import DOCUMENT_ENCODER_MODEL
from heal_app.configs.model_configs import ENABLE_RERANKING_REAL_TIME_FLOW
from heal_app.configs.model_configs import FAST_GEN_AI_MODEL_VERSION
from heal_app.configs.model_configs import GEN_AI_API_ENDPOINT
from heal_app.configs.model_configs import GEN_AI_MODEL_PROVIDER
from heal_app.configs.model_configs import GEN_AI_MODEL_VERSION
from heal_app.llm.factory import get_default_llm
from heal_app.server.features.persona.api import admin_router as admin_persona_router
from heal_app.server.features.persona.api import basic_router as persona_router
from heal_app.server.features.prompt.api import basic_router as prompt_router
from heal_app.server.manage.administrative import router as admin_router
from heal_app.server.manage.get_state import router as state_router
from heal_app.server.manage.users import router as user_router
from heal_app.server.query_and_chat.chat_backend import router as chat_router
from heal_app.utils.logger import setup_logger
from heal_app.utils.telemetry import optional_telemetry
from heal_app.utils.telemetry import RecordType
from heal_app.utils.variable_functionality import fetch_versioned_implementation


logger = setup_logger()


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logger.exception(f"{request}: {exc_str}")
    content = {"status_code": 422, "message": exc_str, "data": None}
    return JSONResponse(content=content, status_code=422)


def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    try:
        raise (exc)
    except Exception:
        # log stacktrace
        logger.exception("ValueError")
    return JSONResponse(
        status_code=400,
        content={"message": str(exc)},
    )


def include_router_with_global_prefix_prepended(
    application: FastAPI, router: APIRouter, **kwargs: Any
) -> None:
    """Adds the global prefix to all routes in the router."""
    processed_global_prefix = f"/{APP_API_PREFIX.strip('/')}" if APP_API_PREFIX else ""

    passed_in_prefix = cast(str | None, kwargs.get("prefix"))
    if passed_in_prefix:
        final_prefix = f"{processed_global_prefix}/{passed_in_prefix.strip('/')}"
    else:
        final_prefix = f"{processed_global_prefix}"
    final_kwargs: dict[str, Any] = {
        **kwargs,
        "prefix": final_prefix,
    }

    application.include_router(router, **final_kwargs)


def get_application() -> FastAPI:
    application = FastAPI(title="Danswer Backend", version=__version__)

    # Phase 1 registers only what a health worker's chat needs. The connector,
    # search, document-set, Slack-bot, GPTs and ingestion routers are retired --
    # every one of them reaches Vespa or the connector fleet. They are not
    # deleted, just no longer mounted; see docs/deprecated/MOVED.md.
    include_router_with_global_prefix_prepended(application, chat_router)
    include_router_with_global_prefix_prepended(application, user_router)
    include_router_with_global_prefix_prepended(application, admin_router)
    include_router_with_global_prefix_prepended(application, persona_router)
    include_router_with_global_prefix_prepended(application, admin_persona_router)
    include_router_with_global_prefix_prepended(application, prompt_router)
    include_router_with_global_prefix_prepended(application, state_router)
    # Approved-source library. Its routes 409 only if a deployment sets
    # KNOWLEDGE_ENABLED=false; `make up` leaves it on.
    include_router_with_global_prefix_prepended(application, knowledge_router)
    # Creating accounts and changing roles. Mounted after `user_router`, which
    # keeps the inherited read-only user routes.
    include_router_with_global_prefix_prepended(application, users_admin_router)
    # Plain-language glosses for a cited passage. Any signed-in user, since it
    # is a reading aid on the answer rather than an admin tool.
    include_router_with_global_prefix_prepended(application, reference_router)

    if AUTH_TYPE == AuthType.DISABLED:
        # Server logs this during auth setup verification step
        pass

    elif AUTH_TYPE == AuthType.BASIC:
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_auth_router(auth_backend),
            prefix="/auth",
            tags=["auth"],
        )
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_register_router(UserRead, UserCreate),
            prefix="/auth",
            tags=["auth"],
        )
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_reset_password_router(),
            prefix="/auth",
            tags=["auth"],
        )
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_verify_router(UserRead),
            prefix="/auth",
            tags=["auth"],
        )
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_users_router(UserRead, UserUpdate),
            prefix="/users",
            tags=["users"],
        )

    elif AUTH_TYPE == AuthType.GOOGLE_OAUTH:
        oauth_client = GoogleOAuth2(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET)
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_oauth_router(
                oauth_client,
                auth_backend,
                SECRET,
                associate_by_email=True,
                is_verified_by_default=True,
                # Points the user back to the login page
                redirect_url=f"{WEB_DOMAIN}/auth/oauth/callback",
            ),
            prefix="/auth/oauth",
            tags=["auth"],
        )
        # Need basic auth router for `logout` endpoint
        include_router_with_global_prefix_prepended(
            application,
            fastapi_users.get_logout_router(auth_backend),
            prefix="/auth",
            tags=["auth"],
        )

    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )

    application.add_exception_handler(ValueError, value_error_handler)

    @application.on_event("startup")
    async def startup_event() -> None:
        verify_auth = fetch_versioned_implementation(
            "heal_app.auth.users", "verify_auth_setting"
        )
        # Will throw exception if an issue is found
        verify_auth()

        # Danswer APIs key
        # Ensure the key exists, but never log its value.
        get_danswer_api_key()

        if OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET:
            logger.info("Both OAuth Client ID and Secret are configured.")

        if DISABLE_GENERATIVE_AI:
            logger.info("Generative AI Q&A disabled")
        else:
            logger.info(f"Using LLM Provider: {GEN_AI_MODEL_PROVIDER}")
            logger.info(f"Using LLM Model Version: {GEN_AI_MODEL_VERSION}")
            if GEN_AI_MODEL_VERSION != FAST_GEN_AI_MODEL_VERSION:
                logger.info(
                    f"Using Fast LLM Model Version: {FAST_GEN_AI_MODEL_VERSION}"
                )
            if GEN_AI_API_ENDPOINT:
                logger.info(f"Using LLM Endpoint: {GEN_AI_API_ENDPOINT}")

            # Any additional model configs logged here
            get_default_llm().log_model_configs()

        if MULTILINGUAL_QUERY_EXPANSION:
            logger.info(
                f"Using multilingual flow with languages: {MULTILINGUAL_QUERY_EXPANSION}"
            )

        if ENABLE_RERANKING_REAL_TIME_FLOW:
            logger.info("Reranking step of search flow is enabled.")

        logger.info(f'Using Embedding model: "{DOCUMENT_ENCODER_MODEL}"')
        if ASYM_QUERY_PREFIX or ASYM_PASSAGE_PREFIX:
            logger.info(f'Query embedding prefix: "{ASYM_QUERY_PREFIX}"')
            logger.info(f'Passage embedding prefix: "{ASYM_PASSAGE_PREFIX}"')

        # Phase 1 boots nothing but the API. What used to happen here and no
        # longer does:
        #   warm_up_models()          embedding + TensorFlow intent models
        #   nltk.download(...)        on every single boot
        #   create_initial_*          seeded connector rows Heal never uses
        #   ensure_indices_exist()    the Vespa hard dependency
        # Retrieval is back, but as one in-process module: the collection and
        # the 384-dim embedding model are prepared on a background thread
        # below, not by a second container.

        logger.info("Loading default Prompts and Personas")
        load_chat_yamls()

        # Only acts on an empty user table. With auth on, this is the one way
        # a fresh deployment gets an account that can log in and create others.
        await ensure_bootstrap_admin()

        logger.info(f"Knowledge retrieval enabled: {heal_config.KNOWLEDGE_ENABLED}")
        # Collection creation and the embedding model load, off the boot path,
        # so the first admin upload does not pay for both.
        prepare_knowledge_store_in_background()
        logger.info(f"Safety prompt version: {heal_config.SAFETY_PROMPT_VERSION}")
        if not heal_config.TRANSLATION_EN_URL or not heal_config.TRANSLATION_LUG_URL:
            logger.warning(
                "Translation endpoints are not configured; Luganda chat will "
                "fail until TRANSLATION_EN_URL and TRANSLATION_LUG_URL are set"
            )

        optional_telemetry(
            record_type=RecordType.VERSION, data={"version": __version__}
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Change this to the list of allowed origins if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return application


app = get_application()


if __name__ == "__main__":
    logger.info(
        f"Starting Danswer Backend version {__version__} on http://{APP_HOST}:{str(APP_PORT)}/"
    )
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
