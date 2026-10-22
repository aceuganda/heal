"""The catalogue of models Heal can be pointed at.

Adding a model is a line here, not a code change at any call site. The plan is
explicit that model choice must be settled by measurement on the clinical eval
set rather than by name, so the catalogue deliberately carries several and
commits to none.
"""
import os

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
        notes="Runs on our own infrastructure. Falls back to the cloud model "
        "when unreachable.",
        base_url=config.SELF_HOSTED_URL,
    )


def _catalogue() -> dict[str, ModelSpec]:
    """The static catalogue plus the self-hosted entry when configured.

    Built per call rather than at import: the endpoint is read from the
    environment, and tests set it after this module is already imported.
    """
    spec = _self_hosted_spec()
    return {**_CATALOGUE, SELF_HOSTED_ID: spec} if spec else dict(_CATALOGUE)


def all_models() -> list[ModelSpec]:
    """Every catalogue entry, including ones not offered to users."""
    return list(_catalogue().values())


def get_model(model_id: str) -> ModelSpec:
    """Look up one model, failing with the ids that do exist."""
    catalogue = _catalogue()
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
        for spec in _catalogue().values()
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
