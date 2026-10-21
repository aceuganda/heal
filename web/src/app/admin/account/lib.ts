/**
 * Password rules for the change-password form.
 *
 * Mirrors `password_problem` in backend heal/server/account_api.py so the form
 * explains a refusal before sending it; the server still decides.
 */

export const MIN_PASSWORD_LENGTH = 8;

const EASY_TO_GUESS = new Set(["password", "admin", "changeme", "heal"]);

export interface PasswordChange {
  current: string;
  next: string;
  confirm: string;
}

export function passwordProblem(
  { current, next, confirm }: PasswordChange,
  email: string
): string | null {
  if (!current) return "Enter your current password.";
  if (next.length < MIN_PASSWORD_LENGTH)
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (next === current)
    return "The new password must be different from the current one.";
  const lowered = next.toLowerCase();
  if (EASY_TO_GUESS.has(lowered) || lowered === email.toLowerCase())
    return "That password is too easy to guess.";
  if (next !== confirm) return "The two new passwords do not match.";
  return null;
}

/** FastAPI sends `detail` as a string, or as a list for validation errors. */
export function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string")
    return detail[0].msg;
  return fallback;
}

export function signedOutMessage(count: number): string {
  if (count === 0) return "Password changed.";
  const sessions = count === 1 ? "1 other session" : `${count} other sessions`;
  return `Password changed. ${sessions} signed out.`;
}
