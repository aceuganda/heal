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
from heal_app.llm.exceptions import GenAIDisabledException
from heal_app.llm.factory import get_default_llm
from heal_app.llm.utils import get_gen_ai_api_key
from heal_app.llm.utils import test_llm
from heal_app.server.models import ApiKey
from heal_app.utils.logger import setup_logger

router = APIRouter(prefix="/manage")
logger = setup_logger()


"""Admin only API endpoints.

The document boost/hide controls and the connector deletion endpoint were
removed here and kept for reference under deprecated/. What remains is the
OpenAI key administration, which Heal keeps.
"""


@router.head("/admin/genai-api-key/validate")
def validate_existing_genai_api_key(
    _: User = Depends(current_admin_user),
) -> None:
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

    try:
        llm = get_default_llm(api_key=genai_api_key, timeout=10)
    except GenAIDisabledException:
        return

    is_valid = test_llm(llm)

    if not is_valid:
        if genai_api_key is None:
            raise HTTPException(status_code=404, detail="Key not found")
        raise HTTPException(status_code=400, detail="Invalid API key provided")

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

        llm = get_default_llm(api_key=request.api_key, timeout=10)
        is_valid = test_llm(llm)

        if not is_valid:
            raise HTTPException(400, "Invalid API key provided")

        get_dynamic_config_store().store(GEN_AI_API_KEY_STORAGE_KEY, request.api_key)
    except GenAIDisabledException:
        # If Disable Generative AI is set, no need to verify, just store the key for later use
        get_dynamic_config_store().store(GEN_AI_API_KEY_STORAGE_KEY, request.api_key)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.delete("/admin/genai-api-key")
def delete_genai_api_key(
    _: User = Depends(current_super_admin_user),
) -> None:
    get_dynamic_config_store().delete(GEN_AI_API_KEY_STORAGE_KEY)
