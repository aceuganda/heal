from heal_app.configs.app_configs import DISABLE_GENERATIVE_AI
from heal_app.configs.chat_configs import QA_TIMEOUT
from heal_app.configs.model_configs import FAST_GEN_AI_MODEL_VERSION
from heal_app.configs.model_configs import GEN_AI_API_ENDPOINT
from heal_app.configs.model_configs import GEN_AI_API_VERSION  # noqa: F401
from heal_app.configs.model_configs import GEN_AI_LLM_PROVIDER_TYPE
from heal_app.configs.model_configs import GEN_AI_MAX_OUTPUT_TOKENS
from heal_app.configs.model_configs import GEN_AI_MODEL_PROVIDER
from heal_app.configs.model_configs import GEN_AI_MODEL_VERSION
from heal_app.configs.model_configs import GEN_AI_TEMPERATURE
from heal_app.llm.chat_llm import DefaultMultiLLM
from heal_app.llm.custom_llm import CustomModelServer
from heal_app.llm.exceptions import GenAIDisabledException
from heal_app.llm.gpt_4_all import DanswerGPT4All
from heal_app.llm.interfaces import LLM
from heal_app.llm.utils import get_gen_ai_api_key


def get_default_llm(
    gen_ai_model_provider: str = GEN_AI_MODEL_PROVIDER,
    api_key: str | None = None,
    timeout: int = QA_TIMEOUT,
    use_fast_llm: bool = False,
    gen_ai_model_version_override: str | None = None,
    api_base: str | None = None,
    custom_llm_provider: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    top_p: float | None = None,
) -> LLM:
    """A single place to fetch the configured LLM for Danswer
    Also allows overriding certain LLM defaults

    `api_base`/`custom_llm_provider` point the client at an OpenAI-compatible
    endpoint we host ourselves; `temperature`/`max_output_tokens`/`top_p` are
    the per-request wording knobs. All of them keep the module defaults when
    omitted, so existing callers are unaffected."""
    if DISABLE_GENERATIVE_AI:
        raise GenAIDisabledException()

    if gen_ai_model_version_override:
        model_version = gen_ai_model_version_override
    else:
        model_version = (
            FAST_GEN_AI_MODEL_VERSION if use_fast_llm else GEN_AI_MODEL_VERSION
        )
    if api_key is None:
        api_key = get_gen_ai_api_key()

    if gen_ai_model_provider.lower() == "custom":
        return CustomModelServer(api_key=api_key, timeout=timeout)

    if gen_ai_model_provider.lower() == "gpt4all":
        return DanswerGPT4All(model_version=model_version, timeout=timeout)

    # Fall back to the module defaults rather than forwarding None, which would
    # overwrite DefaultMultiLLM's own environment-derived values.
    return DefaultMultiLLM(
        model_version=model_version,
        api_key=api_key,
        timeout=timeout,
        api_base=api_base if api_base is not None else GEN_AI_API_ENDPOINT,
        custom_llm_provider=(
            custom_llm_provider
            if custom_llm_provider is not None
            else GEN_AI_LLM_PROVIDER_TYPE
        ),
        temperature=temperature if temperature is not None else GEN_AI_TEMPERATURE,
        max_output_tokens=(
            max_output_tokens
            if max_output_tokens is not None
            else GEN_AI_MAX_OUTPUT_TOKENS
        ),
        # Forwarded as None when unset so the client leaves nucleus sampling to
        # the provider's own default rather than pinning it to 1.0.
        top_p=top_p,
    )
