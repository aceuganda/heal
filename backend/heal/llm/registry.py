"""The catalogue of models Heal can be pointed at.

Adding a model is a line here, not a code change at any call site. The plan is
explicit that model choice must be settled by measurement on the clinical eval
set rather than by name, so the catalogue deliberately carries several and
commits to none.
"""
import os
import time

from heal import config
from heal.llm.models import ModelSpec
from heal.logger import get_logger

logger = get_logger(__name__)

_CATALOGUE: dict[str, ModelSpec] = {
    spec.id: spec
    for spec in [
        ModelSpec(
            id="gpt-4o-mini",
            display_name="GPT-4o mini",
            provider="openai",
            model_name="gpt-4o-mini",
            context_tokens=128_000,
            notes="Default. Cheap enough for classification and chat both.",
        ),
        ModelSpec(
            id="gpt-4o",
            display_name="GPT-4o",
            provider="openai",
            model_name="gpt-4o",
            context_tokens=128_000,
            notes="Stronger clinical reasoning; measure the cost before enabling.",
        ),
        ModelSpec(
            id="gpt-3.5-turbo",
            display_name="GPT-3.5 Turbo",
            provider="openai",
            model_name="gpt-3.5-turbo",
            context_tokens=16_385,
            selectable=False,
            notes="The inherited default. Kept only as an eval baseline.",
        ),
        ModelSpec(
            id="claude-sonnet-4-5",
            display_name="Claude Sonnet 4.5",
            provider="anthropic",
            model_name="claude-sonnet-4-5",
            context_tokens=200_000,
            notes="Alternative provider; requires ANTHROPIC_API_KEY.",
        ),
    ]
}

# The id the self-hosted endpoint is registered under. Stable regardless of
# which model is actually being served, so HEAL_CHAT_MODEL=self-hosted keeps
# working when the internal box is re-pointed at a different checkpoint.
SELF_HOSTED_ID = "self-hosted"


def _self_hosted_spec() -> ModelSpec | None:
    """The internal endpoint as a catalogue entry, if one is configured."""
    if not config.self_hosted_configured():
        return None
    return ModelSpec(
        id=SELF_HOSTED_ID,
        display_name="Internal model",
        # OpenAI-compatible wire format; the base_url is what makes it ours.
        provider="openai",
        model_name=config.SELF_HOSTED_MODEL,
        context_tokens=config.SELF_HOSTED_CONTEXT_TOKENS,
        notes="Runs on our own infrastructure. "
        + (
            "Falls back to the cloud model when unreachable."
            if config.SELF_HOSTED_CLOUD_FALLBACK
            else "Never falls back to the cloud."
        ),
        base_url=config.SELF_HOSTED_URL,
    )


# How long OpenAI's model list is trusted before asking again. The list changes
# a few times a year; a pod restart is not needed to see a new one.
OPENAI_LIST_TTL_SECONDS = 600
# A failed listing is remembered for less time, so a fixed key shows up soon
# without every admin page load waiting on a timeout in the meantime.
OPENAI_LIST_RETRY_SECONDS = 60

# Ids that answer chat completions. OpenAI's /models also returns embeddings,
# speech, image and moderation models, none of which can write an answer.
_OPENAI_CHAT_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")
_OPENAI_NOT_CHAT = (
    "audio",
    "realtime",
    "tts",
    "transcribe",
    "image",
    "search",
    "instruct",
    "embedding",
)

_openai_cache: dict[str, object] = {"at": 0.0, "ttl": 0.0, "specs": {}}


def _openai_key() -> str | None:
    """The OpenAI key the chat client already uses -- never a separate one.

    Same resolution as the LLM factory: a key saved from the admin Keys page
    wins, the environment is behind it. Imported lazily because it reaches the
    config store.
    """
    try:
        from heal_app.llm.utils import get_gen_ai_api_key

        key = get_gen_ai_api_key()
    except Exception:  # noqa: BLE001 -- no store means fall through to env
        key = None
    return key or os.environ.get("OPENAI_API_KEY") or None


def _fetch_openai_models(api_key: str) -> list[str]:
    """Model ids from OpenAI's own listing. Raises on any failure."""
    import requests

    response = requests.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=5,
    )
    response.raise_for_status()
    return [str(entry.get("id", "")) for entry in response.json().get("data", [])]


def _is_chat_model(model_id: str) -> bool:
    return model_id.startswith(_OPENAI_CHAT_PREFIXES) and not any(
        word in model_id for word in _OPENAI_NOT_CHAT
    )


def _openai_specs() -> dict[str, ModelSpec]:
    """OpenAI's chat models as catalogue entries, cached.

    Never raises: a bad key or no network leaves the static entries, which is
    what this deployment offered before the listing existed.
    """
    now = time.monotonic()
    if now - float(_openai_cache["at"]) < float(_openai_cache["ttl"]):
        return _openai_cache["specs"]  # type: ignore[return-value]

    specs: dict[str, ModelSpec] = {}
    ttl = OPENAI_LIST_RETRY_SECONDS
    # Local mode sends nothing to OpenAI, not even a listing. The static
    # entries still let an admin switch back to a cloud model.
    key = None if local_only() else _openai_key()
    if key:
        try:
            ids = _fetch_openai_models(key)
            specs = {
                model_id: ModelSpec(
                    id=model_id,
                    display_name=model_id,
                    provider="openai",
                    model_name=model_id,
                    # The listing carries no context size; this is the floor of
                    # every current chat model, so history is never over-sent.
                    context_tokens=128_000,
                    notes="Listed live by OpenAI.",
                )
                for model_id in sorted(ids)
                if _is_chat_model(model_id)
            }
            ttl = OPENAI_LIST_TTL_SECONDS
        except Exception as exc:  # noqa: BLE001 -- see docstring
            logger.warning("Could not list OpenAI models: %s", type(exc).__name__)

    _openai_cache.update(at=now, ttl=ttl, specs=specs)
    return specs


def _catalogue(include_remote: bool = False) -> dict[str, ModelSpec]:
    """The static catalogue plus the self-hosted entry when configured.

    Built per call rather than at import: the endpoint is read from the
    environment, and tests set it after this module is already imported.

    `include_remote` adds OpenAI's live list. Off for the per-message lookups,
    so answering a health worker never waits on a listing call; the static
    entries win over a live one with the same id.
    """
    spec = _self_hosted_spec()
    remote = _openai_specs() if include_remote else {}
    catalogue = {**remote, **_CATALOGUE}
    return {**catalogue, SELF_HOSTED_ID: spec} if spec else catalogue


def all_models() -> list[ModelSpec]:
    """Every catalogue entry, including ones not offered to users."""
    return list(_catalogue(include_remote=True).values())


def get_model(model_id: str) -> ModelSpec:
    """Look up one model, failing with the ids that do exist.

    The static catalogue answers first; OpenAI's listing is only consulted for
    an id it does not know, which is a model an admin picked from that list.
    """
    catalogue = _catalogue()
    if model_id in catalogue:
        return catalogue[model_id]
    catalogue = _catalogue(include_remote=True)
    try:
        return catalogue[model_id]
    except KeyError:
        raise ValueError(
            f"Unknown model '{model_id}'. Known: {', '.join(sorted(catalogue))}"
        ) from None


def _provider_configured(spec: ModelSpec) -> bool:
    """A model is only offerable if its provider has a key in the environment."""
    # We host it; there is no third-party key to hold. Whether it can actually
    # be reached is a runtime question, answered by the failover, not here --
    # hiding it from the list when the box is briefly down would be worse.
    if spec.self_hosted:
        return True
    if os.environ.get(spec.api_key_env):
        return True
    # The inherited config keeps the OpenAI key under its own name.
    return spec.provider == "openai" and bool(os.environ.get("GEN_AI_API_KEY"))


def available_models() -> list[ModelSpec]:
    """Models a user may actually choose right now.

    Filtered by the catalogue's own `selectable` flag, by the optional
    HEAL_ENABLED_CHAT_MODELS allowlist, and by whether the provider has a key.
    """
    allowlist = {m.strip() for m in config.ENABLED_CHAT_MODELS.split(",") if m.strip()}
    return [
        spec
        for spec in _catalogue(include_remote=True).values()
        if spec.selectable
        and (not allowlist or spec.id in allowlist)
        and _provider_configured(spec)
    ]


def _configured(name: str, fallback: str) -> str:
    """A model id from the deployment's settings, environment behind it.

    Imported inside the function rather than at module scope: `heal.llm.defaults`
    reaches the database, and nothing that merely names a model should load the
    ORM to do it. A lookup that fails there returns the environment's value, so
    an unreachable database never costs a health worker an answer.
    """
    from heal.llm import defaults

    return str(defaults.effective().get(name) or fallback)


def local_only() -> bool:
    """True when the deployment answers on the self-hosted model.

    Then no process may call OpenAI: not naming, not glossing, not listing.
    Reads the saved id rather than resolving it, so it never triggers the
    OpenAI listing it exists to suppress.
    """
    return (
        config.self_hosted_configured()
        and _configured("chat_model", config.CHAT_MODEL) == SELF_HOSTED_ID
    )


def default_model() -> ModelSpec:
    """The chat model this deployment answers with.

    Falls back to the environment's model if the saved id no longer resolves --
    a model removed from the catalogue must not take the chat path down with
    it, and answering on the configured model is the safe reading of "the saved
    choice is no longer available".
    """
    chosen = _configured("chat_model", config.CHAT_MODEL)
    try:
        return get_model(chosen)
    except ValueError:
        logger.error(
            "Saved chat model '%s' is not in the catalogue; using %s",
            chosen,
            config.CHAT_MODEL,
        )
        return get_model(config.CHAT_MODEL)


def classifier_model() -> ModelSpec:
    """The model used for intent classification and other short internal calls."""
    chosen = _configured("classifier_model", config.CLASSIFIER_MODEL)
    try:
        return get_model(chosen)
    except ValueError:
        logger.error(
            "Saved classifier model '%s' is not in the catalogue; using %s",
            chosen,
            config.CLASSIFIER_MODEL,
        )
        return get_model(config.CLASSIFIER_MODEL)


def classifier_for(chat_model_id: str | None = None) -> ModelSpec:
    """The model that understands a question answered by `chat_model_id`.

    The internal model does both jobs when it is the one answering: a question
    meant to stay on our own infrastructure must not be sent to a cloud
    classifier first, and a cloud key should not be needed to use it. Any
    other chat model keeps the configured classifier.
    """
    chat = get_model(chat_model_id) if chat_model_id else default_model()
    return chat if chat.self_hosted else classifier_model()
