/**
 * Profile rules, mirrored from backend/heal/accounts/profile.py so the form
 * can say what is wrong before sending. The server's check is the one that
 * is enforced; keep the two in step.
 */

export const MAX_ORGANISATION_LENGTH = 200;
export const MIN_AGE_YEARS = 16;
const EARLIEST_BIRTH_YEAR = 1900;

/** Mirrors SEX_OPTIONS in profile.py. Sign-up needs them before there is a
 * session to fetch them with. */
export const SEX_OPTIONS: Record<string, string> = {
  female: "Female",
  male: "Male",
  prefer_not_to_say: "Prefer not to say",
};

export interface ProfileDraft {
  organisation: string;
  /** yyyy-mm-dd, as an <input type="date"> gives it. */
  date_of_birth: string;
  sex: string;
}

export interface ProfileView {
  email: string;
  organisation: string | null;
  date_of_birth: string | null;
  sex: string | null;
  sex_options: Record<string, string>;
  email_verified: boolean;
  admin_verified: boolean;
  admin_verified_at: string | null;
  chat_blocked: boolean;
  access_blocked_reason: string | null;
}

function ageOn(birth: Date, today: Date): number {
  const beforeBirthday =
    today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() &&
      today.getDate() < birth.getDate());
  return today.getFullYear() - birth.getFullYear() - (beforeBirthday ? 1 : 0);
}

/** Why this profile cannot be saved, or null. */
export function profileProblem(
  draft: ProfileDraft,
  sexOptions: Record<string, string>,
  today: Date = new Date()
): string | null {
  const organisation = draft.organisation.trim();
  if (!organisation) return "Enter the organisation you work for.";
  if (organisation.length > MAX_ORGANISATION_LENGTH) {
    return `Keep the organisation under ${MAX_ORGANISATION_LENGTH} characters.`;
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(draft.date_of_birth);
  if (!match) return "Enter your date of birth.";
  // Built from parts, not parsed: `new Date("1990-05-01")` is UTC midnight
  // and reads as the 30th of April west of Greenwich.
  const birth = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3])
  );
  const startOfToday = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate()
  );
  if (birth.getFullYear() < EARLIEST_BIRTH_YEAR || birth >= startOfToday) {
    return "Enter a real date of birth.";
  }
  if (ageOn(birth, today) < MIN_AGE_YEARS) {
    return `Heal accounts are for people aged ${MIN_AGE_YEARS} or over.`;
  }

  if (!(draft.sex in sexOptions)) return "Choose one of the options for sex.";
  return null;
}

/** The message to show for a failed sign-up response body. */
export function signupErrorMessage(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail === "REGISTER_USER_ALREADY_EXISTS") {
    return "An account already exists with the specified email.";
  }
  if (detail === "REGISTER_INVALID_PASSWORD") {
    return "That password is not allowed. Try a longer one.";
  }
  // A 422 from the profile check: pydantic prefixes the rule's own sentence.
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
    return detail[0].msg.replace(/^Value error, /, "");
  }
  if (typeof detail === "string") return detail;
  return "Unknown error";
}
