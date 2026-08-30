"""The service API key.

Lifted out of `danswer/server/danswer_api/ingestion.py`. That module also
carries the connector ingestion endpoints, which reach the indexing pipeline and
therefore Vespa -- importing it just to read a key pulled the whole retired
stack into the boot path.

The key itself is unchanged, including its storage location, so existing
deployments keep working.
"""
import secrets

from heal.logger import get_logger
from heal_app.dynamic_configs import get_dynamic_config_store
from heal_app.dynamic_configs.interface import ConfigNotFoundError

logger = get_logger(__name__)

_DANSWER_API_KEY = "danswer_api_key"


def get_danswer_api_key(key_len: int = 30, dont_regenerate: bool = False) -> str | None:
    """Read the API key, generating one on first use."""
    kv_store = get_dynamic_config_store()
    try:
        return str(kv_store.load(_DANSWER_API_KEY))
    except ConfigNotFoundError:
        if dont_regenerate:
            return None

    logger.info("Generating service API key")
    api_key = "dn_" + secrets.token_urlsafe(key_len)
    kv_store.store(_DANSWER_API_KEY, api_key)
    return api_key


def delete_danswer_api_key() -> None:
    kv_store = get_dynamic_config_store()
    try:
        kv_store.delete(_DANSWER_API_KEY)
    except ConfigNotFoundError:
        pass
