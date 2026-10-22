"""Chat session export.

Heal-added feature, moved out of `danswer/chat/process_message.py` so that the
export survives the retirement of that module. Behaviour is unchanged.
"""
from fastapi.responses import JSONResponse
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from heal.logger import get_logger
from heal_app.db.chat import get_chat_messages_by_session
from heal_app.db.models import ChatSession

logger = get_logger(__name__)


def download_chat_sessions_helper(db_session: Session) -> JSONResponse:
    """Every chat session with its messages, for clinical review."""
    try:
        all_sessions = (
            db_session.query(ChatSession).options(joinedload(ChatSession.user)).all()
        )
        sessions_with_messages = []

        for session in all_sessions:
            user_email = session.user.email if session.user else None
            messages = get_chat_messages_by_session(
                session.id, None, db_session=db_session, skip_permission_check=True
            )
            sessions_with_messages.append(
                {
                    "session_id": session.id,
                    "session_description": session.description,
                    "user_email": user_email,
                    "messages": [
                        {
                            "message_type": message.message_type,
                            "message": message.message,
                            "luganda_message": message.luganda_message,
                        }
                        for message in messages
                    ],
                }
            )

        return JSONResponse(content=sessions_with_messages)

    except Exception as e:
        # The export carries chat content, so the failure is logged without it.
        logger.exception(f"Failed to build chat session export: {type(e).__name__}")
        raise RuntimeError("Failed to download chat sessions") from e
