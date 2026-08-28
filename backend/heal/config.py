"""Environment-driven configuration for Heal modules.

Rule: no network address is ever written in source. Every host, port and key is
read from the environment so that deployments can be moved, rotated or made
private without a code change. Missing values fail loudly at call time with an
actionable message rather than falling back to a shared default.
"""
import os


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


#####
# Translation services
#
# Heal runs two private machine-translation services: one Luganda->English, one
# English->Luganda. Under Design A these are the only models Luganda text ever
# touches -- retrieval and generation happen entirely in English.
#####

# Provider implementation to use. "heal_mt" is the private MT pair; other
# providers can be registered without touching call sites.
TRANSLATION_PROVIDER = _env_str("TRANSLATION_PROVIDER", "heal_mt")

# Base URLs, no trailing slash. Required when the heal_mt provider is active.
TRANSLATION_EN_URL = _env_str("TRANSLATION_EN_URL").rstrip("/")
TRANSLATION_LUG_URL = _env_str("TRANSLATION_LUG_URL").rstrip("/")

# Optional bearer token, sent to both services. The current deployment has no
# auth at all; this exists so that turning it on is a config change.
TRANSLATION_API_KEY = _env_str("TRANSLATION_API_KEY")

# The old code had no timeout, so a hung MT service hung the whole chat request.
TRANSLATION_CONNECT_TIMEOUT = _env_float("TRANSLATION_CONNECT_TIMEOUT", 5.0)
TRANSLATION_READ_TIMEOUT = _env_float("TRANSLATION_READ_TIMEOUT", 60.0)

# Retries apply to connection-level failures only, never to a partially
# streamed response -- replaying one would duplicate text in the user's answer.
TRANSLATION_MAX_RETRIES = _env_int("TRANSLATION_MAX_RETRIES", 2)
TRANSLATION_RETRY_BACKOFF = _env_float("TRANSLATION_RETRY_BACKOFF", 0.5)

# Per-token pacing when streaming a translation to the browser. Purely cosmetic:
# it keeps the Luganda answer arriving at a readable speed rather than in one
# burst. Set to 0 to disable.
TRANSLATION_STREAM_DELAY = _env_float("TRANSLATION_STREAM_DELAY", 0.09)
