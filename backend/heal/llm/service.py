"""Resolving a catalogue entry to a usable LLM client.

The client itself is still Danswer's LiteLLM wrapper -- it already speaks to
every provider in the catalogue, so replacing it would be churn. What is new is
that the *choice* of model is explicit and named, rather than read straight from
two environment variables at the call site.
"""
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from heal import config
from heal.llm.models import ModelSpec
from heal.llm.registry import default_model
from heal.llm.registry import get_model


def to_provider_messages(messages: Sequence[tuple[str, str]]) -> list[Any]:
    """Provider-neutral (role, text) pairs -> the client's message objects.

    This is the only place that knows about LangChain, which is why
    PromptBuilder can be built and tested without it.
    """
    from langchain.schema.messages import AIMessage
    from langchain.schema.messages import HumanMessage
    from langchain.schema.messages import SystemMessage

    kinds = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return [kinds[role](content=text) for role, text in messages]


def get_llm(model_id: str | None = None, timeout: int | None = None) -> Any:
    """Return a client for the named model, or the configured default."""
    spec = get_model(model_id) if model_id else default_model()
    return build_llm(spec, timeout=timeout)


def build_llm(spec: ModelSpec, timeout: int | None = None) -> Any:
    """Construct a client for an explicit spec.

    Imported lazily: the provider stack pulls in LiteLLM and LangChain, and
    nothing that merely selects a model should have to load them.
    """
    from heal_app.llm.factory import get_default_llm

    return get_default_llm(
        gen_ai_model_provider=spec.provider,
        timeout=timeout if timeout is not None else config.LLM_TIMEOUT,
        gen_ai_model_version_override=spec.model_name,
    )


@lru_cache(maxsize=4)
def _cached_llm(model_id: str, timeout: int) -> Any:
    return build_llm(get_model(model_id), timeout=timeout)


def get_classifier_llm(model_id: str | None = None) -> Any:
    """Client for short internal calls such as intent classification.

    Cached because it is built on every message and the clients are stateless.

    `model_id` names a different classifier for one call. It exists for the
    admin playground, which compares classifiers without changing the one every
    live conversation is using; omitted, this is the configured default.
    """
    return _cached_llm(model_id or config.CLASSIFIER_MODEL, config.LLM_TIMEOUT)
