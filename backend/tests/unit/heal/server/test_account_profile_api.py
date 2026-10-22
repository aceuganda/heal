"""Your own profile, the verification email, and the admin access switches."""
import datetime
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from heal.accounts import access
from heal.accounts.access import Policy
from heal.server import account_api
from heal.server import users_api
from heal_app.auth import users as users_mod
from heal_app.auth.roles import UserRole
from heal_app.auth.users import current_account_user
from heal_app.auth.users import current_user
from heal_app.auth.users import EmailNotConfigured
from heal_app.auth.users import get_user_manager


def make_user(role=UserRole.MEMBER, **extra):
    base = dict(
        id=uuid.uuid4(),
        email="nurse@clinic.test",
        role=role,
        is_verified=False,
        admin_verified_at=None,
        admin_verified_by_id=None,
        chat_blocked=False,
        organisation=None,
        date_of_birth=None,
        sex=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


class FakeSession:
    def __init__(self, row) -> None:
        self.row = row
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, model, key):
        return self.row if key == self.row.id else None

    def add(self, obj) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture(autouse=True)
def open_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access, "current_policy", lambda refresh=False: Policy())
    monkeypatch.setattr(users_mod, "DISABLE_AUTH", False)


#####
# Profile
#####


def account_client(user, manager=None) -> TestClient:
    app = FastAPI()
    app.include_router(account_api.router)
    app.dependency_overrides[current_account_user] = lambda: user
    if manager is not None:
        app.dependency_overrides[get_user_manager] = lambda: manager
    return TestClient(app)


class TestProfile:
    def test_a_new_account_is_unverified_at_both_levels(self) -> None:
        body = account_client(make_user()).get("/manage/me/profile").json()
        assert body["email_verified"] is False
        assert body["admin_verified"] is False
        assert body["access_blocked_reason"] is None

    def test_a_valid_profile_is_saved(self, monkeypatch) -> None:
        user = make_user()
        session = FakeSession(user)
        monkeypatch.setattr(account_api, "_open_session", lambda: session)
        response = account_client(user).put(
            "/manage/me/profile",
            json={
                "organisation": "  Mulago Hospital ",
                "date_of_birth": "1990-05-01",
                "sex": "female",
            },
        )
        assert response.status_code == 200, response.text
        assert user.organisation == "Mulago Hospital"
        assert user.date_of_birth == datetime.date(1990, 5, 1)
        assert session.committed

    def test_an_invalid_profile_is_refused_before_writing(self, monkeypatch) -> None:
        user = make_user()
        session = FakeSession(user)
        monkeypatch.setattr(account_api, "_open_session", lambda: session)
        response = account_client(user).put(
            "/manage/me/profile",
            json={"organisation": "", "date_of_birth": "1990-05-01", "sex": "female"},
        )
        assert response.status_code == 422
        assert not session.committed


class FakeManager:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def request_verify(self, user, request=None) -> None:
        self.calls += 1
        if self.error:
            raise self.error


class TestVerificationEmail:
    def test_sends_when_mail_works(self) -> None:
        manager = FakeManager()
        response = account_client(make_user(), manager).post(
            "/manage/me/request-verification"
        )
        assert response.json() == {"status": "sent"}
        assert manager.calls == 1

    def test_no_mail_server_is_a_readable_503(self) -> None:
        manager = FakeManager(EmailNotConfigured("placeholder SMTP"))
        response = account_client(make_user(), manager).post(
            "/manage/me/request-verification"
        )
        assert response.status_code == 503
        assert "administrator" in response.json()["detail"]

    def test_an_already_verified_account_sends_nothing(self) -> None:
        manager = FakeManager()
        response = account_client(make_user(is_verified=True), manager).post(
            "/manage/me/request-verification"
        )
        assert response.json() == {"status": "already_verified"}
        assert manager.calls == 0


#####
# Admin switches
#####


def admin_client(actor) -> TestClient:
    app = FastAPI()
    app.include_router(users_api.router)
    app.include_router(users_api.policy_router)
    app.dependency_overrides[current_user] = lambda: actor
    return TestClient(app)


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    user = make_user()
    monkeypatch.setattr(users_api, "AsyncSession", lambda *a, **k: FakeSession(user))
    return user


class TestAdminAccess:
    def test_a_member_cannot_verify_anyone(self, target) -> None:
        response = admin_client(make_user()).patch(
            f"/manage/users/{target.id}/access", json={"admin_verified": True}
        )
        assert response.status_code == 403
        assert target.admin_verified_at is None

    def test_an_admin_verification_records_who_and_when(self, target) -> None:
        admin = make_user(role=UserRole.ADMIN, email="admin@clinic.test")
        response = admin_client(admin).patch(
            f"/manage/users/{target.id}/access", json={"admin_verified": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["admin_verified"] is True
        assert target.admin_verified_at is not None
        assert target.admin_verified_by_id == admin.id

    def test_unverifying_clears_who_and_when(self, target) -> None:
        target.admin_verified_at = datetime.datetime.now(datetime.timezone.utc)
        target.admin_verified_by_id = uuid.uuid4()
        admin_client(make_user(role=UserRole.ADMIN)).patch(
            f"/manage/users/{target.id}/access", json={"admin_verified": False}
        )
        assert target.admin_verified_at is None
        assert target.admin_verified_by_id is None

    def test_email_verification_and_chat_block_are_set_independently(
        self, target
    ) -> None:
        admin_client(make_user(role=UserRole.ADMIN)).patch(
            f"/manage/users/{target.id}/access",
            json={"email_verified": True, "chat_blocked": True},
        )
        assert target.is_verified is True
        assert target.chat_blocked is True
        assert target.admin_verified_at is None

    def test_an_empty_change_is_refused(self, target) -> None:
        response = admin_client(make_user(role=UserRole.ADMIN)).patch(
            f"/manage/users/{target.id}/access", json={}
        )
        assert response.status_code == 422


class TestPolicyEndpoints:
    def test_only_sent_switches_are_saved(self, monkeypatch) -> None:
        saved: list = []

        def fake_save(values, actor_id):
            saved.append(values)
            return Policy(block_admin_unverified=True)

        monkeypatch.setattr(access, "save", fake_save)
        response = admin_client(make_user(role=UserRole.ADMIN)).put(
            "/manage/access-policy", json={"block_admin_unverified": True}
        )
        assert response.status_code == 200, response.text
        assert saved == [{"block_admin_unverified": True}]
        assert response.json()["block_email_unverified"] is False

    def test_a_member_cannot_change_the_policy(self) -> None:
        response = admin_client(make_user()).put(
            "/manage/access-policy", json={"block_admin_unverified": True}
        )
        assert response.status_code == 403
