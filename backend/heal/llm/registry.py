"""The catalogue of models Heal can be pointed at.

Adding a model is a line here, not a code change at any call site. The plan is
explicit that model choice must be settled by measurement on the clinical eval
set rather than by name, so the catalogue deliberately carries several and
commits to none.
"""
import os

from heal import config
from heal.llm.models import ModelSpec

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


def all_models() -> list[ModelSpec]:
    """Every catalogue entry, including ones not offered to users."""
    return list(_CATALOGUE.values())


def get_model(model_id: str) -> ModelSpec:
    """Look up one model, failing with the ids that do exist."""
    try:
        return _CATALOGUE[model_id]
    except KeyError:
        raise ValueError(
            f"Unknown model '{model_id}'. Known: {', '.join(sorted(_CATALOGUE))}"
        ) from None


def _provider_configured(spec: ModelSpec) -> bool:
    """A model is only offerable if its provider has a key in the environment."""
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
        for spec in _CATALOGUE.values()
        if spec.selectable
        and (not allowlist or spec.id in allowlist)
        and _provider_configured(spec)
    ]


def default_model() -> ModelSpec:
    """The configured chat model."""
    return get_model(config.CHAT_MODEL)


def classifier_model() -> ModelSpec:
    """The model used for intent classification and other short internal calls."""
    return get_model(config.CLASSIFIER_MODEL)
