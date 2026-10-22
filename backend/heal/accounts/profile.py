"""What a person may put on their own profile, checked in one place.

Mirrored in web/src/app/account/lib.ts so the form can say what is wrong
before a round trip; this module is the one that is enforced.
"""
import datetime

SEX_OPTIONS: dict[str, str] = {
    "female": "Female",
    "male": "Male",
    "prefer_not_to_say": "Prefer not to say",
}

MAX_ORGANISATION_LENGTH = 200

# Heal is used by health workers, not children. The floor stops a typo in the
# year (2025 for 1985) from being saved as a real date of birth.
MIN_AGE_YEARS = 16
EARLIEST_BIRTH_YEAR = 1900


def _age_on(birth: datetime.date, today: datetime.date) -> int:
    before_birthday = (today.month, today.day) < (birth.month, birth.day)
    return today.year - birth.year - int(before_birthday)


def profile_problem(
    organisation: str,
    date_of_birth: datetime.date,
    sex: str,
    today: datetime.date | None = None,
) -> str | None:
    """Why this profile cannot be saved, or None."""
    today = today or datetime.date.today()
    if not organisation.strip():
        return "Enter the organisation you work for."
    if len(organisation.strip()) > MAX_ORGANISATION_LENGTH:
        return f"Keep the organisation under {MAX_ORGANISATION_LENGTH} characters."
    if date_of_birth.year < EARLIEST_BIRTH_YEAR or date_of_birth >= today:
        return "Enter a real date of birth."
    if _age_on(date_of_birth, today) < MIN_AGE_YEARS:
        return f"Heal accounts are for people aged {MIN_AGE_YEARS} or over."
    if sex not in SEX_OPTIONS:
        return "Choose one of the options for sex."
    return None
