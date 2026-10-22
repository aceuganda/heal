"""Resolving a catalogue entry to a usable LLM client.

The client itself is still Danswer's LiteLLM wrapper -- it already speaks to
every provider in the catalogue, so replacing it would be churn. What is new is
that the *choice* of model is explicit and named, rather than read straight from
two environment variables at the call site.
"""
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from typing import TYPE_CHECKING

from heal import config
from heal.llm.models import ModelSpec
from heal.llm.registry import default_model
from heal.llm.registry import get_model
from heal.logger import get_logger

if TYPE_CHECKING:
    from heal.llm.settings import GenerationSettings

logger = get_logger(__name__)

# Attempts against the internal endpoint before giving up on it for this
# message. Two, because the common failure is one dropped connection rather
# than a box that is genuinely down, and a second try costs a second.
SELF_HOSTED_ATTEMPTS = 2


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


def build_llm(
    spec: ModelSpec,
    timeout: int | None = None,
    generation: "GenerationSettings | None" = None,
) -> Any:
    """Construct a client for an explicit spec.

    Imported lazily: the provider stack pulls in LiteLLM and LangChain, and
    nothing that merely selects a model should have to load them.

    `generation` is one request's wording knobs. Omitted, it reads the
    deployment's own constants, which is what every chat turn does.
    """
    from heal.llm.settings import GenerationSettings
    from heal_app.llm.factory import get_default_llm

    seconds = timeout if timeout is not None else config.LLM_TIMEOUT
    gen = generation or GenerationSettings()

    # `token_cap`, not `max_output_tokens`: the verbosity level may lower the
    # ceiling, and it may never raise it above what the deployment configured.
    if spec.self_hosted:
        # `custom_llm_provider` is what stops LiteLLM prefixing the model name
        # and routing to OpenAI's own servers instead of ours. The key is a
        # placeholder the endpoint ignores but the client insists on.
        return get_default_llm(
            gen_ai_model_provider=spec.provider,
            api_key=config.SELF_HOSTED_API_KEY,
            timeout=seconds,
            gen_ai_model_version_override=spec.model_name,
            api_base=spec.base_url,
            custom_llm_provider="openai",
            temperature=gen.temperature,
            max_output_tokens=gen.token_cap,
            top_p=gen.top_p,
        )

    return get_default_llm(
        gen_ai_model_provider=spec.provider,
        timeout=seconds,
        gen_ai_model_version_override=spec.model_name,
        temperature=gen.temperature,
        max_output_tokens=gen.token_cap,
        top_p=gen.top_p,
    )


@dataclass
class Generation:
    """Which model actually produced a stream.

    Resolved as the stream runs, so it is only complete once the stream has
    been consumed -- read it when auditing, not before. `model_id` is the model
    that answered, NOT the one that was asked for: an audit that records the
    request rather than the outcome cannot explain who wrote a dosage answer.
    """

    model_id: str
    failed_over: bool = False
    attempts: int = 0


def stream_with_failover(
    model_id: str | None = None,
    messages: Sequence[tuple[str, str]] | None = None,
    timeout: int | None = None,
    generation_settings: "GenerationSettings | None" = None,
) -> tuple[Iterator[str], Generation]:
    """Stream from the requested model, falling back to the cloud model.

    `generation_settings` is passed by a caller that has already resolved them
    -- the agent does, because the same verbosity level that sets the token cap
    also writes a line into the prompt, and reading them twice could produce
    two different answers to one question if a save landed in between.

    The internal endpoint gets SELF_HOSTED_ATTEMPTS tries. If none of them
    produce a first token, the configured cloud model answers instead and the
    returned `Generation` records that it happened.

    The fallback can only happen BEFORE the first token. Once text has reached
    the user, swapping models mid-answer would splice two different models'
    words into one clinical answer, so a failure after that point is a failure.
    """
    spec = get_model(model_id) if model_id else default_model()
    generation = Generation(model_id=spec.id)
    provider_messages = to_provider_messages(messages or [])

    def run() -> Iterator[str]:
        if spec.self_hosted:
            for attempt in range(1, SELF_HOSTED_ATTEMPTS + 1):
                generation.attempts = attempt
                try:
                    yield from _stream_once(
                        spec, provider_messages, timeout, generation_settings
                    )
                    return
                except Exception as exc:  # noqa: BLE001 -- any failure falls back
                    logger.warning(
                        "Self-hosted model attempt %d/%d failed: %s",
                        attempt,
                        SELF_HOSTED_ATTEMPTS,
                        type(exc).__name__,
                    )

            fallback = _fallback_spec(spec)
            logger.error(
                "Self-hosted model unreachable after %d attempts; using %s",
                SELF_HOSTED_ATTEMPTS,
                fallback.id,
            )
            generation.model_id = fallback.id
            generation.failed_over = True
            yield from _stream_once(
                fallback, provider_messages, timeout, generation_settings
            )
            return

        generation.attempts = 1
        yield from _stream_once(spec, provider_messages, timeout, generation_settings)

    return run(), generation


def _stream_once(
    spec: ModelSpec,
    provider_messages: list[Any],
    timeout: int | None,
    generation_settings: "GenerationSettings | None" = None,
) -> Iterator[str]:
    """One streaming attempt against one model.

    The first token is pulled inside this function so that a connection error
    surfaces here, where the caller can still choose another model, rather than
    part-way through a half-written answer.
    """
    llm = build_llm(spec, timeout=timeout, generation=generation_settings)
    yield from llm.stream(provider_messages)


def _fallback_spec(failed: ModelSpec) -> ModelSpec:
    """The cloud model to use when the internal one cannot be reached.

    Never another self-hosted entry: the point of the fallback is to leave our
    own infrastructure, so falling back onto it would defeat it.
    """
    candidate = default_model()
    if candidate.self_hosted or candidate.id == failed.id:
        return get_model(config.CLASSIFIER_MODEL)
    return candidate


def probe_self_hosted(timeout: int = 5) -> dict[str, Any]:
    """Ask the internal endpoint what it is serving.

    Used by the admin surfaces to show that a configured endpoint is actually
    answering, and what it is answering with. Never raises: "unreachable" is an
    ordinary answer here, not an error.
    """
    if not config.self_hosted_configured():
        return {"configured": False, "reachable": False, "models": []}

    import requests

    try:
        response = requests.get(
            f"{config.SELF_HOSTED_URL.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {config.SELF_HOSTED_API_KEY}"},
            timeout=timeout,
        )
        response.raise_for_status()
        entries = response.json().get("data", [])
    except Exception as exc:  # noqa: BLE001 -- a status probe must not raise
        return {
            "configured": True,
            "reachable": False,
            "error": type(exc).__name__,
            "models": [],
        }

    return {
        "configured": True,
        "reachable": True,
        "models": [
            {
                "id": entry.get("id", ""),
                "context_tokens": entry.get("max_model_len"),
                "served_by": entry.get("owned_by", ""),
            }
            for entry in entries
        ],
        # The configured model must be one the server actually serves. A
        # mismatch answers "why does every call 404" before it is asked.
        "serves_configured_model": any(
            entry.get("id") == config.SELF_HOSTED_MODEL for entry in entries
        ),
    }


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
