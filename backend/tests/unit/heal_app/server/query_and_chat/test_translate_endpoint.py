from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from heal.language import TranslationUnavailable
from heal_app.server.query_and_chat import chat_backend
from heal_app.server.query_and_chat.models import TranslateChatMessagePayload


class _Session:
    committed = False

    def commit(self) -> None:
        self.committed = True


class _Failing:
    def to_luganda(self, text: str) -> str:
        raise TranslationUnavailable(
            "Translation service rejected the request (HTTP 404)"
        )


def test_a_translation_failure_is_a_503_with_a_readable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = SimpleNamespace(message="Take one tablet.", luganda_message=None)
    monkeypatch.setattr(chat_backend, "get_chat_message", lambda **kw: message)
    monkeypatch.setattr(chat_backend, "get_language_service", lambda: _Failing())
    session = _Session()

    with pytest.raises(HTTPException) as caught:
        chat_backend.upd_chat_message(
            TranslateChatMessagePayload(message_id=1), user=None, db_session=session
        )

    assert caught.value.status_code == 503
    # The user-facing sentence, never the HTTP detail from the MT service.
    assert "404" not in caught.value.detail
    assert message.luganda_message is None
    assert not session.committed
