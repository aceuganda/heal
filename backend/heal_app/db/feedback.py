from uuid import UUID

from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import select
from sqlalchemy.orm import Session

from heal_app.configs.constants import MessageType
from heal_app.db.chat import get_chat_message
from heal_app.db.models import ChatMessageFeedback
from heal_app.db.models import Document as DbDocument


def fetch_db_doc_by_id(doc_id: str, db_session: Session) -> DbDocument:
    stmt = select(DbDocument).where(DbDocument.id == doc_id)
    result = db_session.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise ValueError("Invalid Document ID Provided")

    return doc


def fetch_docs_ranked_by_boost(
    db_session: Session, ascending: bool = False, limit: int = 100
) -> list[DbDocument]:
    order_func = asc if ascending else desc
    stmt = (
        select(DbDocument)
        .order_by(order_func(DbDocument.boost), order_func(DbDocument.semantic_id))
        .limit(limit)
    )
    result = db_session.execute(stmt)
    doc_list = result.scalars().all()

    return list(doc_list)


def create_chat_message_feedback(
    is_positive: bool | None,
    feedback_text: str | None,
    chat_message_id: int,
    user_id: UUID | None,
    db_session: Session,
    # Slack user requested help from human
    required_followup: bool | None = None,
) -> None:
    if is_positive is None and feedback_text is None and required_followup is None:
        raise ValueError("No feedback provided")

    chat_message = get_chat_message(
        chat_message_id=chat_message_id, user_id=user_id, db_session=db_session
    )

    if chat_message.message_type != MessageType.ASSISTANT:
        raise ValueError("Can only provide feedback on LLM Outputs")

    message_feedback = ChatMessageFeedback(
        chat_message_id=chat_message_id,
        is_positive=is_positive,
        feedback_text=feedback_text,
        required_followup=required_followup,
    )

    db_session.add(message_feedback)
    db_session.commit()
