from heal_app.chat.chat_utils import combine_message_chain
from heal_app.db.models import ChatMessage
from heal_app.llm.interfaces import LLM
from heal_app.llm.utils import dict_based_prompt_to_langchain_prompt
from heal_app.prompts.chat_prompts import CHAT_NAMING
from heal_app.utils.logger import setup_logger

logger = setup_logger()

# Long enough to recognise a conversation in the sidebar, short enough to fit.
FALLBACK_NAME_CHARS = 60


def _fallback_name(full_history: list[ChatMessage]) -> str:
    first = full_history[0].message.strip() if full_history else ""
    if len(first) <= FALLBACK_NAME_CHARS:
        return first
    return first[:FALLBACK_NAME_CHARS].rstrip() + "…"


def get_renamed_conversation_name(
    full_history: list[ChatMessage],
    llm: LLM | None = None,
) -> str:
    """A short title for a conversation.

    Uses the model that classifies for the deployment's chat model, so a
    deployment answering on the internal model names its chats there too and
    never needs a cloud key. Never raises: a title is cosmetic, and a failure
    here must not surface as an error after the answer already arrived.
    """

    def get_chat_rename_messages(history_str: str) -> list[dict[str, str]]:
        messages = [
            {
                "role": "user",
                "content": CHAT_NAMING.format(chat_history=history_str),
            },
        ]
        return messages

    try:
        if llm is None:
            from heal.llm import classifier_for
            from heal.llm import get_llm

            llm = get_llm(classifier_for().id)

        history_str = combine_message_chain(full_history)
        prompt_msgs = get_chat_rename_messages(history_str)
        filled_llm_prompt = dict_based_prompt_to_langchain_prompt(prompt_msgs)
        new_name = llm.invoke(filled_llm_prompt).strip().strip(' "')
    except Exception as e:  # noqa: BLE001 -- see docstring
        logger.warning(f"Chat naming failed, using first message: {type(e).__name__}")
        return _fallback_name(full_history)

    logger.debug(f"New Session Name: {new_name}")

    return new_name or _fallback_name(full_history)
