"""The access policy: what blocks whom, and what never blocks anyone."""
import asyncio
import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from heal.accounts import access
from heal.accounts.access import ADMIN_UNVERIFIED_MESSAGE
from heal.accounts.access import blocked_reason
from heal.accounts.access import EMAIL_UNVERIFIED_MESSAGE
from heal.accounts.access import Policy
from heal_app.auth import users as users_mod
from heal_app.auth.roles import UserRole
from heal_app.server.query_and_chat import chat_backend

BOTH = Policy(block_email_unverified=True, block_admin_unverified=True)
NOW = datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc)


def member(email_verified=False, admin_verified=False, chat_blocked=False):
    return SimpleNamespace(
        role=UserRole.MEMBER,
        is_verified=email_verified,
        admin_verified_at=NOW if admin_verified else None,
        chat_blocked=chat_blocked,
    )


class TestBlockedReason:
    def test_nothing_is_blocked_by_default(self) -> None:
        assert blocked_reason(member(), Policy()) is None

    def test_email_block_applies_only_to_email_unverified(self) -> None:
        policy = Policy(block_email_unverified=True)
        assert blocked_reason(member(), policy) == EMAIL_UNVERIFIED_MESSAGE
        assert blocked_reason(member(email_verified=True), policy) is None

    def test_admin_block_applies_only_to_admin_unverified(self) -> None:
        policy = Policy(block_admin_unverified=True)
        assert blocked_reason(member(email_verified=True), policy) == (
            ADMIN_UNVERIFIED_MESSAGE
        )
        assert blocked_reason(member(admin_verified=True), policy) is None

    def test_email_is_asked_for_first_when_both_are_missing(self) -> None:
        # It is the one the person can fix themselves.
        assert blocked_reason(member(), BOTH) == EMAIL_UNVERIFIED_MESSAGE

    def test_a_fully_verified_member_passes_both(self) -> None:
        user = member(email_verified=True, admin_verified=True)
        assert blocked_reason(user, BOTH) is None

    @pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPER_ADMIN])
    def test_admins_are_never_blocked(self, role: UserRole) -> None:
        admin = SimpleNamespace(role=role, is_verified=False, admin_verified_at=None)
        assert blocked_reason(admin, BOTH) is None


class TestPolicyRead:
    def test_an_unreadable_policy_blocks_nobody(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom():
            raise RuntimeError("database down")

        access.invalidate()
        monkeypatch.setattr(
            "heal_app.db.engine.get_sqlalchemy_engine", boom, raising=True
        )
        assert access.current_policy(refresh=True) == Policy()
        access.invalidate()


class TestEnforcement:
    def test_current_user_refuses_a_blocked_member(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(access, "current_policy", lambda refresh=False: BOTH)
        with pytest.raises(HTTPException) as caught:
            asyncio.run(users_mod.current_user(user=member()))
        assert caught.value.status_code == 403
        assert caught.value.detail == EMAIL_UNVERIFIED_MESSAGE

    def test_current_user_lets_a_verified_member_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(access, "current_policy", lambda refresh=False: BOTH)
        user = member(email_verified=True, admin_verified=True)
        assert asyncio.run(users_mod.current_user(user=user)) is user

    def test_a_chat_block_refuses_new_questions(self) -> None:
        with pytest.raises(HTTPException) as caught:
            asyncio.run(chat_backend.current_chat_user(user=member(chat_blocked=True)))
        assert caught.value.status_code == 403

    def test_no_chat_block_passes(self) -> None:
        user = member()
        assert asyncio.run(chat_backend.current_chat_user(user=user)) is user
