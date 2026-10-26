from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import cast

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from heal_app.auth.users import current_admin_user
from heal_app.auth.users import current_super_admin_user
from heal_app.configs.app_configs import GENERATIVE_MODEL_ACCESS_CHECK_FREQ
from heal_app.configs.constants import GEN_AI_API_KEY_STORAGE_KEY
from heal_app.db.models import User
from heal_app.dynamic_configs import get_dynamic_config_store
from heal_app.dynamic_configs.interface import ConfigNotFoundError
from heal_app.llm.factory import get_default_llm
from heal_app.llm.utils import get_gen_ai_api_key
from heal_app.server.models import ApiKey
from heal_app.utils.logger import setup_logger

router = APIRouter(prefix="/manage")
logger = setup_logger()

OPENAI_KEY_VALIDATION_MODEL = "gpt-5.4-mini"


def _validate_openai_key(api_key: str) -> None:
    """Check the key against the model this deployment wants to use.

    Do not use the inherited GEN_AI_MODEL_VERSION here: production may leave
    it unset, in which case the legacy gpt-3.5-turbo default rejects a valid
    key before it can be saved. Pin the validation call to OpenAI and remove
    any compatible-provider endpoint overrides from the environment.
    """
    try:
        llm = get_default_llm(
            gen_ai_model_provider="openai",
            api_key=api_key,
            timeout=15,
            gen_ai_model_version_override=OPENAI_KEY_VALIDATION_MODEL,
            api_base=None,
            custom_llm_provider=None,
            temperature=0,
            max_output_tokens=8,
            use_configured_endpoint=False,
            use_configured_provider=False,
        )
        response = llm.invoke("Reply with OK.")
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("OpenAI returned an empty validation response")
    except Exception as exc:  # noqa: BLE001 -- report provider validation details
        detail = str(exc).replace(api_key, "[redacted]").strip()
        if len(detail) > 400:
            detail = detail[:400] + "…"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not validate this key with {OPENAI_KEY_VALIDATION_MODEL}: "
                f"{type(exc).__name__}: {detail or 'request failed'}"
            ),
        ) from exc


"""Admin only API endpoints.

The document boost/hide controls and the connector deletion endpoint were
removed here and kept for reference under deprecated/. What remains is the
OpenAI key administration, which Heal keeps.
"""


@router.head("/admin/genai-api-key/validate")
def validate_existing_genai_api_key(
    _: User = Depends(current_admin_user),
) -> None:
    # A self-hosted deployment has no OpenAI key to check, and checking one
    # would be exactly the call local mode promises not to make.
    from heal.llm.registry import local_only

    if local_only():
        return

    # Only validate every so often
    check_key_time = "genai_api_key_last_check_time"
    kv_store = get_dynamic_config_store()
    curr_time = datetime.now(tz=timezone.utc)
    try:
        last_check = datetime.fromtimestamp(
            cast(float, kv_store.load(check_key_time)), tz=timezone.utc
        )
        check_freq_sec = timedelta(seconds=GENERATIVE_MODEL_ACCESS_CHECK_FREQ)
        if curr_time - last_check < check_freq_sec:
            return
    except ConfigNotFoundError:
        # First time checking the key, nothing unusual
        pass

    genai_api_key = get_gen_ai_api_key()

    if genai_api_key is None:
        raise HTTPException(status_code=404, detail="Key not found")

    _validate_openai_key(genai_api_key)

    # Mark check as successful
    get_dynamic_config_store().store(check_key_time, curr_time.timestamp())


@router.get("/admin/genai-api-key", response_model=ApiKey)
def get_gen_ai_api_key_from_dynamic_config_store(
    _: User = Depends(current_super_admin_user),
) -> ApiKey:
    """
    NOTE: Only gets value from dynamic config store as to not expose env variables.
    """
    try:
        # only get last 4 characters of key to not expose full key
        return ApiKey(
            api_key=cast(
                str, get_dynamic_config_store().load(GEN_AI_API_KEY_STORAGE_KEY)
            )[-4:]
        )
    except ConfigNotFoundError:
        raise HTTPException(status_code=404, detail="Key not found")


@router.put("/admin/genai-api-key")
def store_genai_api_key(
    request: ApiKey,
    _: User = Depends(current_super_admin_user),
) -> None:
    try:
        if not request.api_key:
            raise HTTPException(400, "No API key provided")

        _validate_openai_key(request.api_key)
        get_dynamic_config_store().store(GEN_AI_API_KEY_STORAGE_KEY, request.api_key)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.delete("/admin/genai-api-key")
def delete_genai_api_key(
    _: User = Depends(current_super_admin_user),
) -> None:
    get_dynamic_config_store().delete(GEN_AI_API_KEY_STORAGE_KEY)
