"""Tests for the role hierarchy.

These pin authorisation decisions, so they are written as statements about who
can do what rather than about the implementation. The one that matters most is
the first: an equality check against ADMIN locks super admins out of every
screen they own, and that mistake looks harmless in review.
"""
import pytest

from heal_app.auth.roles import ASSIGNABLE_ROLES
from heal_app.auth.roles import PRIVILEGED_ROLE
from heal_app.auth.roles import role_at_least
from heal_app.auth.roles import UserRole


class TestHierarchy:
    def test_a_super_admin_satisfies_an_admin_check(self) -> None:
        """The lockout bug. SUPER_ADMIN outranks ADMIN and must pass its gate."""
        assert role_at_least(UserRole.SUPER_ADMIN, UserRole.ADMIN)

    def test_an_admin_does_not_satisfy_a_super_admin_check(self) -> None:
        """The tiers are stored distinctly even while the gate admits both."""
        assert not role_at_least(UserRole.ADMIN, UserRole.SUPER_ADMIN)

    def test_a_member_satisfies_nothing_above_itself(self) -> None:
        assert role_at_least(UserRole.MEMBER, UserRole.MEMBER)
        assert not role_at_least(UserRole.MEMBER, UserRole.ADMIN)
        assert not role_at_least(UserRole.MEMBER, UserRole.SUPER_ADMIN)

    def test_every_role_satisfies_itself(self) -> None:
        for role in UserRole:
            assert role_at_least(role, role)

    def test_no_role_means_no_authority(self) -> None:
        """An unauthenticated caller has no role; that must not pass a gate."""
        assert not role_at_least(None, UserRole.MEMBER)
        assert not role_at_least(None, UserRole.ADMIN)


class TestLegacyBasicRole:
    """`basic` is what `member` used to be called.

    Rows written before migration a1c4f7d2e9b0 still hold it, and reading a
    value the enum does not know raises LookupError -- which would be every
    existing user unable to log in.
    """

    def test_basic_is_still_a_known_role(self) -> None:
        assert UserRole("basic") is UserRole.BASIC

    def test_basic_carries_exactly_member_authority(self) -> None:
        assert role_at_least(UserRole.BASIC, UserRole.MEMBER)
        assert not role_at_least(UserRole.BASIC, UserRole.ADMIN)

    def test_basic_is_never_offered_as_a_choice(self) -> None:
        """It exists to be read, not to be handed out."""
        assert UserRole.BASIC not in ASSIGNABLE_ROLES


class TestAssignableRoles:
    def test_the_three_real_tiers_are_assignable(self) -> None:
        assert set(ASSIGNABLE_ROLES) == {
            UserRole.MEMBER,
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
        }

    @pytest.mark.parametrize("role", ASSIGNABLE_ROLES)
    def test_every_assignable_role_is_ranked(self, role: UserRole) -> None:
        """An unranked role would silently evaluate as the lowest authority."""
        assert role_at_least(role, UserRole.MEMBER)


class TestPrivilegedGate:
    """API keys, creating users and changing roles.

    Deliberately loosened: an ADMIN currently passes. This test exists so that
    tightening `PRIVILEGED_ROLE` to SUPER_ADMIN is a conscious edit here rather
    than a silent change in who can spend money on the deployment.
    """

    def test_an_admin_currently_holds_privileged_powers(self) -> None:
        assert role_at_least(UserRole.ADMIN, PRIVILEGED_ROLE)

    def test_a_super_admin_always_holds_privileged_powers(self) -> None:
        assert role_at_least(UserRole.SUPER_ADMIN, PRIVILEGED_ROLE)

    def test_a_member_never_holds_privileged_powers(self) -> None:
        assert not role_at_least(UserRole.MEMBER, PRIVILEGED_ROLE)
        assert not role_at_least(UserRole.BASIC, PRIVILEGED_ROLE)
