"""Chat titles follow the deployment's model and never fail the request."""
from types import SimpleNamespace
from typing import Any

import pytest

from heal import config
from heal_app.secondary_llm_flows import chat_session_naming
from heal_app.secondary_llm_flows.chat_session_naming import (
    get_renamed_conversation_name,
)


def _history(text: str) -> list[Any]:
    return [SimpleNamespace(message=text, message_type="user")]


class _Boom:
    def invoke(self, prompt: Any) -> str:
        raise ConnectionError("no route to host")


class _Fixed:
    def invoke(self, prompt: Any) -> str:
        return ' "Malaria dosing" '


@pytest.fixture(autouse=True)
def flat_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_session_naming,
        "combine_message_chain",
        lambda msgs: "\n".join(m.message for m in msgs),
    )


def test_uses_the_model_reply() -> None:
    assert get_renamed_conversation_name(_history("hi"), llm=_Fixed()) == (
        "Malaria dosing"
    )


def test_model_failure_falls_back_to_first_message() -> None:
    long = "What is the dose of artemether for a child of 12kg " * 3
    name = get_renamed_conversation_name(_history(long), llm=_Boom())
    assert name.startswith("What is the dose")
    assert len(name) <= chat_session_naming.FALLBACK_NAME_CHARS + 1


def test_self_hosted_chat_names_on_the_internal_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "SELF_HOSTED_URL", "http://internal.test/v1")
    monkeypatch.setattr(config, "SELF_HOSTED_MODEL", "local-model")
    monkeypatch.setattr(config, "CHAT_MODEL", "self-hosted")
    asked: list[str] = []

    def fake_get_llm(model_id: str | None = None, timeout: int | None = None) -> Any:
        asked.append(model_id or "")
        return _Fixed()

    import heal.llm

    monkeypatch.setattr(heal.llm, "get_llm", fake_get_llm)
    get_renamed_conversation_name(_history("hi"))
    assert asked == ["self-hosted"]
