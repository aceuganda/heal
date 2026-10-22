"""Tests for changing your own password.

What must hold: the old password is required, a weak or unchanged password is
refused before anything is written, and a change signs out every session except
the one that made it.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_users.password import PasswordHelper

from heal.server import account_api
from heal_app.auth.users import cookie_transport
from heal_app.auth.users import current_account_user

CURRENT = "first-boot-pass"
helper = PasswordHelper()


class FakeRow:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.email = "admin@heal.test"
        self.hashed_password = helper.hash(CURRENT)


class FakeResult:
    rowcount = 2


class FakeSession:
    def __init__(self, row: FakeRow) -> None:
        self.row = row
        self.statements: list = []
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, model, key):
        return self.row if key == self.row.id else None

    def add(self, obj) -> None:
        pass

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult()

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
def row() -> FakeRow:
    return FakeRow()


@pytest.fixture
def session(row: FakeRow, monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    fake = FakeSession(row)
    monkeypatch.setattr(account_api, "_open_session", lambda: fake)
    return fake


def client_for(user) -> TestClient:
    app = FastAPI()
    app.include_router(account_api.router)
    app.dependency_overrides[current_account_user] = lambda: user
    return TestClient(app)


def change(client: TestClient, current: str, new: str, cookie: str | None = None):
    if cookie:
        client.cookies.set(cookie_transport.cookie_name, cookie)
    return client.post(
        "/manage/me/password",
        json={"current_password": current, "new_password": new},
    )


class TestPasswordProblem:
    def test_accepts_a_reasonable_password(self) -> None:
        assert account_api.password_problem(CURRENT, "clinic-rota-42", "a@b.c") is None

    @pytest.mark.parametrize(
        "new, reason",
        [
            ("short", "at least 8"),
            (CURRENT, "different"),
            ("Password", "easy to guess"),
            ("a@b.test", "easy to guess"),
        ],
    )
    def test_refuses(self, new: str, reason: str) -> None:
        problem = account_api.password_problem(CURRENT, new, "A@b.test")
        assert problem is not None and reason in problem


class TestChangeOwnPassword:
    def test_changes_the_hash_and_keeps_this_session(self, row, session) -> None:
        response = change(client_for(row), CURRENT, "clinic-rota-42", cookie="mine")

        assert response.status_code == 200
        assert response.json() == {"signed_out_sessions": 2}
        assert helper.verify_and_update("clinic-rota-42", row.hashed_password)[0]
        assert session.committed
        (statement,) = session.statements
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "accesstoken.token != 'mine'" in compiled

    def test_without_a_cookie_ends_every_session(self, row, session) -> None:
        change(client_for(row), CURRENT, "clinic-rota-42")

        (statement,) = session.statements
        assert "accesstoken.token" not in str(statement)

    def test_wrong_current_password_changes_nothing(self, row, session) -> None:
        before = row.hashed_password
        response = change(client_for(row), "guess", "clinic-rota-42")

        assert response.status_code == 400
        assert row.hashed_password == before
        assert not session.statements and not session.committed

    def test_weak_new_password_changes_nothing(self, row, session) -> None:
        before = row.hashed_password
        response = change(client_for(row), CURRENT, "admin")

        assert response.status_code == 422
        assert "at least 8" in response.json()["detail"]
        assert row.hashed_password == before and not session.committed

    def test_needs_a_signed_in_account(self, session) -> None:
        response = change(client_for(None), CURRENT, "clinic-rota-42")

        assert response.status_code == 403
        assert not session.committed
