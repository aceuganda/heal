"""Sign-up carries the profile, checked by the same rule as the profile page."""
import datetime

import pytest
from pydantic import ValidationError

from heal_app.auth.schemas import UserCreate

PROFILE = {
    "organisation": "  Mulago Hospital ",
    "date_of_birth": "1990-05-01",
    "sex": "female",
}


def signup(**over) -> UserCreate:
    return UserCreate(email="nurse@example.org", password="long-enough-pw", **over)


class TestSignupProfile:
    def test_a_complete_profile_is_accepted_and_trimmed(self) -> None:
        user = signup(**PROFILE)
        assert user.organisation == "Mulago Hospital"
        assert user.date_of_birth == datetime.date(1990, 5, 1)
        assert user.sex == "female"

    def test_the_profile_reaches_the_row_on_a_safe_create(self) -> None:
        # fastapi-users' register route builds the row from this dict.
        row = signup(**PROFILE).create_update_dict()
        assert row["organisation"] == "Mulago Hospital"
        assert row["date_of_birth"] == datetime.date(1990, 5, 1)
        assert row["sex"] == "female"

    def test_no_profile_is_still_allowed(self) -> None:
        # The bootstrap admin and admin-created accounts have none.
        user = signup()
        assert user.organisation is None and user.sex is None

    def test_half_a_profile_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="date of birth"):
            signup(organisation="Mulago Hospital", sex="female")

    def test_the_shared_rule_is_applied(self) -> None:
        with pytest.raises(ValidationError, match="16"):
            signup(**{**PROFILE, "date_of_birth": "2025-01-01"})
        with pytest.raises(ValidationError, match="sex"):
            signup(**{**PROFILE, "sex": "unknown"})
        with pytest.raises(ValidationError, match="organisation"):
            signup(**{**PROFILE, "organisation": "   "})
