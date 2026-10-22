import datetime

from heal.accounts.profile import profile_problem

TODAY = datetime.date(2026, 10, 22)


def problem(org="Mulago Hospital", dob=datetime.date(1990, 5, 1), sex="female"):
    return profile_problem(org, dob, sex, today=TODAY)


def test_a_complete_profile_is_accepted() -> None:
    assert problem() is None


def test_organisation_is_required() -> None:
    assert "organisation" in problem(org="   ")


def test_a_date_of_birth_in_the_future_is_refused() -> None:
    assert problem(dob=datetime.date(2030, 1, 1)) == "Enter a real date of birth."


def test_a_typo_in_the_year_is_refused_as_too_young() -> None:
    # 2025 typed for 1985.
    assert "16" in problem(dob=datetime.date(2025, 1, 1))


def test_sixteenth_birthday_counts_on_the_day() -> None:
    assert problem(dob=datetime.date(2010, 10, 22)) is None
    assert problem(dob=datetime.date(2010, 10, 23)) is not None


def test_an_unknown_sex_value_is_refused() -> None:
    assert problem(sex="unknown") is not None
