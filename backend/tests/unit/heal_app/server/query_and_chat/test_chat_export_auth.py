"""The all-chats export is clinical data: admins only, never anonymous."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from heal_app.auth import users as users_mod
from heal_app.auth.roles import UserRole
from heal_app.auth.users import current_user
from heal_app.db.engine import get_session
from heal_app.server.query_and_chat import chat_backend


@pytest.fixture(autouse=True)
def auth_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_mod, "DISABLE_AUTH", False)
    monkeypatch.setattr(
        chat_backend,
        "download_chat_sessions_helper",
        lambda db_session: JSONResponse({"sessions": []}),
    )


def client_as(user: object) -> TestClient:
    app = FastAPI()
    app.include_router(chat_backend.router)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app)


def test_a_member_cannot_export_everyone_s_chats() -> None:
    member = SimpleNamespace(role=UserRole.MEMBER)
    assert client_as(member).get("/chat/user-chats").status_code == 403


def test_an_anonymous_caller_cannot_export() -> None:
    assert client_as(None).get("/chat/user-chats").status_code == 403


def test_an_admin_can_export() -> None:
    admin = SimpleNamespace(role=UserRole.ADMIN)
    assert client_as(admin).get("/chat/user-chats").status_code == 200
