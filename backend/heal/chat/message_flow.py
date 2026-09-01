"""The Phase 1 chat flow.

Replaces `danswer/chat/process_message.py::stream_chat_message` -- 543 lines
with ten inline branches, none of which could be tested without Vespa running.

The wire format is deliberately identical. The frontend keeps calling the same
endpoint with the same payload and keeps receiving the same newline-delimited
JSON packets, so Week 1 changes nothing the browser can see.

What is gone: retrieval, the search-mode switch, query rephrasing, the LLM chunk
filter, `check_if_need_search`, and every Vespa import.
"""
from collections.abc import Iterator

from sqlalchemy.orm import Session

from heal.chat.citations import build_citations
from heal.chat.stream_processing import extract_citations
from heal.language import get_language_service
from heal.language import TranslationError
from heal.logger import get_logger
from heal.medical_guidance import AgentRequest
from heal.medical_guidance import MedicalGuidanceAgent
from heal_app.chat.chat_utils import create_chat_chain
from heal_app.chat.models import DanswerAnswerPiece
from heal_app.chat.models import StreamingError
from heal_app.configs.constants import MessageType
from heal_app.db.chat import create_new_chat_message
from heal_app.db.chat import get_chat_message
from heal_app.db.chat import get_chat_session_by_id
from heal_app.db.chat import get_or_create_root_message
from heal_app.db.chat import translate_db_message_to_chat_message_detail
from heal_app.db.models import User
from heal_app.llm.utils import get_default_llm_token_encode
from heal_app.server.query_and_chat.models import CreateChatMessageRequest
from heal_app.server.utils import get_json_line

logger = get_logger(__name__)


def _history_pairs(messages: list) -> list[tuple[bool, str]]:
    """Stored chain -> (is_user, text) pairs, oldest first.

    The English text is used in both directions: a Luganda conversation is
    stored with its English translation, and English is what the model reasons
    over.
    """
    pairs: list[tuple[bool, str]] = []
    for msg in messages:
        if not msg.message:
            continue
        if msg.message_type == MessageType.SYSTEM:
            continue
        pairs.append((msg.message_type == MessageType.USER, msg.message))
    return pairs


def stream_chat_message(
    new_msg_req: CreateChatMessageRequest,
    user: User | None,
    db_session: Session,
) -> Iterator[str]:
    """Answer one chat message, streaming JSON lines to the browser."""
    user_id = user.id if user is not None else None
    language_service = get_language_service()
    is_luganda = language_service.is_luganda(new_msg_req.language)

    try:
        # Access check: raises if the session is missing or not this user's.
        get_chat_session_by_id(
            chat_session_id=new_msg_req.chat_session_id,
            user_id=user_id,
            db_session=db_session,
        )

        # Design A: translate in, then work entirely in English.
        message_text = new_msg_req.message
        luganda_message = None
        if is_luganda:
            luganda_message = message_text
            message_text = language_service.to_english(message_text)

    except TranslationError as e:
        logger.error(f"Inbound translation failed: {e}")
        yield get_json_line(StreamingError(error=e.user_message).dict())
        return
    except Exception as e:
        logger.exception(f"Could not start chat message: {e}")
        yield get_json_line(
            StreamingError(error="Could not start this message.").dict()
        )
        return

    llm_tokenizer = get_default_llm_token_encode()

    # Every chat session begins with an empty root message.
    root_message = get_or_create_root_message(
        chat_session_id=new_msg_req.chat_session_id, db_session=db_session
    )
    if new_msg_req.parent_message_id is not None:
        parent_message = get_chat_message(
            chat_message_id=new_msg_req.parent_message_id,
            user_id=user_id,
            db_session=db_session,
        )
    else:
        parent_message = root_message

    new_user_message = create_new_chat_message(
        chat_session_id=new_msg_req.chat_session_id,
        parent_message=parent_message,
        prompt_id=new_msg_req.prompt_id,
        message=message_text,
        language=new_msg_req.language,
        luganda_message=luganda_message,
        token_count=len(llm_tokenizer(message_text)),
        message_type=MessageType.USER,
        db_session=db_session,
        commit=False,
    )

    final_msg, history_msgs = create_chat_chain(
        chat_session_id=new_msg_req.chat_session_id, db_session=db_session
    )
    if final_msg.id != new_user_message.id:
        db_session.rollback()
        raise RuntimeError(
            "The new message was not on the mainline. "
            "Be sure to update the chat pointers before calling this."
        )
    db_session.commit()

    # ---- answer ----------------------------------------------------------
    agent = MedicalGuidanceAgent()
    tokens, decision = agent.answer(
        AgentRequest(
            message=message_text,
            history=_history_pairs(history_msgs),
            language=new_msg_req.language,
            chat_session_id=new_msg_req.chat_session_id,
            message_id=new_user_message.id,
            model_id=None,
        )
    )

    error: str | None = None
    try:
        if is_luganda:
            # The English answer is produced in full first, then translated and
            # streamed. Translating token by token would mangle grammar.
            for _ in tokens:
                pass
        else:
            for token in tokens:
                yield get_json_line(DanswerAnswerPiece(answer_piece=token).dict())
    except Exception as e:
        logger.exception(f"Generation failed: {e}")
        error = str(e)
        yield get_json_line(
            StreamingError(error="The assistant could not answer. Try again.").dict()
        )

    english_answer = decision.text

    luganda_response: str | None = None
    if is_luganda and not error:
        luganda_response = ""
        try:
            for token in language_service.stream_to_luganda(english_answer):
                luganda_response += token
                yield get_json_line(DanswerAnswerPiece(answer_piece=token).dict())
        except TranslationError as e:
            logger.error(f"Outbound translation failed: {e}")
            yield get_json_line(StreamingError(error=e.user_message).dict())
            error = e.user_message

    # ---- citations -------------------------------------------------------
    # Only the markers the answer actually wrote. `decision.chunks` is in
    # citation order, so [1] is the first passage the prompt was given.
    reference_docs, citations = build_citations(
        db_session=db_session,
        chunks=decision.chunks,
        cited_numbers=extract_citations(english_answer),
    )

    # ---- persist ---------------------------------------------------------
    gen_ai_response_message = create_new_chat_message(
        chat_session_id=new_msg_req.chat_session_id,
        parent_message=new_user_message,
        prompt_id=new_msg_req.prompt_id,
        message=english_answer,
        language=new_msg_req.language,
        luganda_message=luganda_response,
        token_count=len(llm_tokenizer(english_answer)),
        message_type=MessageType.ASSISTANT,
        error=error,
        reference_docs=reference_docs,
        citations=citations,
        db_session=db_session,
        commit=True,
    )

    logger.info(
        f"Answered session={new_msg_req.chat_session_id} "
        f"intent={decision.intent.value} answered={decision.answered} "
        f"citations={len(citations)}"
    )

    yield get_json_line(
        translate_db_message_to_chat_message_detail(gen_ai_response_message).dict()
    )
