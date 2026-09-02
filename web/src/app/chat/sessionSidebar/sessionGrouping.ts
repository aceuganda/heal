/**
 * How the chat sidebar orders and dates a health worker's past sessions.
 *
 * Kept apart from `../lib` and from the components so both can be checked
 * without a DOM. Every function here takes `now` as an argument rather than
 * reading the clock: a grouping that is right at 14:00 and wrong at 00:30 is
 * exactly the bug this replaced, and it cannot be tested at all if the
 * boundary it depends on is unreachable.
 */
import { ChatSession } from "../interfaces";

/** In render order. The sidebar walks this, so it is also the order the
 *  headings appear in. */
export const SESSION_GROUPS = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Previous 30 days",
  "Older",
] as const;

export type SessionGroup = (typeof SESSION_GROUPS)[number];

/** Whole days between two instants, counted by calendar date rather than by
 *  elapsed time. 23:59 last night and 00:01 this morning are two minutes
 *  apart and belong on different days; the old code divided a millisecond
 *  span by 86_400_000 and filed last night's chat under Today. */
function calendarDaysAgo(then: Date, now: Date): number {
  const startOfThen = new Date(
    then.getFullYear(),
    then.getMonth(),
    then.getDate()
  ).getTime();
  const startOfNow = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  ).getTime();
  // Divided from midnight to midnight, so a DST shift inside the span cannot
  // push the result to a fraction and round the wrong way.
  return Math.round((startOfNow - startOfThen) / 86_400_000);
}

export function groupForSession(timeCreated: string, now: Date): SessionGroup {
  const created = new Date(timeCreated);
  if (Number.isNaN(created.getTime())) {
    // A row Heal cannot date still has to be reachable. "Older" is the
    // honest bucket: it makes no claim about when.
    return "Older";
  }

  // A session dated in the future is clock skew between the server and this
  // device, not a scheduled chat. Treated as today rather than hidden in a
  // bucket nobody scrolls to.
  const days = Math.max(calendarDaysAgo(created, now), 0);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 7) return "Previous 7 days";
  if (days <= 30) return "Previous 30 days";
  return "Older";
}

/**
 * Sessions bucketed by age, newest first inside each bucket.
 *
 * Every group is present in the returned record even when empty, so the
 * caller renders headings from a fixed order rather than from whatever order
 * the object happens to have been built in.
 */
export function groupSessionsByDateRange(
  chatSessions: ChatSession[],
  now: Date = new Date()
): Record<SessionGroup, ChatSession[]> {
  const groups = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    "Previous 30 days": [],
    Older: [],
  } as Record<SessionGroup, ChatSession[]>;

  for (const chatSession of chatSessions) {
    groups[groupForSession(chatSession.time_created, now)].push(chatSession);
  }

  // The API's order is not guaranteed, and a sidebar that lists this
  // morning's chat under last Tuesday's is not a list anybody can scan.
  for (const group of SESSION_GROUPS) {
    groups[group].sort(
      (a, b) =>
        new Date(b.time_created).getTime() - new Date(a.time_created).getTime()
    );
  }

  return groups;
}

const TIME = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});
const DAY_MONTH = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
});
const DAY_MONTH_YEAR = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/**
 * When a session was started, in the least text that still answers it.
 *
 * Scaled to the group it will be read under: a row inside "Today" needs the
 * clock time and nothing else, one inside "Previous 30 days" needs the date
 * and would be actively confused by a time. The year appears only once a
 * session is old enough for it to be in doubt.
 *
 * Empty string for a timestamp that will not parse — the row renders without
 * a date rather than with "Invalid Date" under a clinical conversation.
 */
export function formatSessionStart(timeCreated: string, now: Date = new Date()): string {
  const created = new Date(timeCreated);
  if (Number.isNaN(created.getTime())) {
    return "";
  }

  const days = Math.max(calendarDaysAgo(created, now), 0);
  if (days === 0) return TIME.format(created);
  if (days === 1) return `Yesterday ${TIME.format(created)}`;
  if (created.getFullYear() === now.getFullYear()) return DAY_MONTH.format(created);
  return DAY_MONTH_YEAR.format(created);
}

/** The full timestamp, for a `title` a reader can hover when the short form
 *  is not enough — an audit question about a specific conversation needs the
 *  date and the time, not "Yesterday". */
export function fullSessionStart(timeCreated: string): string {
  const created = new Date(timeCreated);
  return Number.isNaN(created.getTime())
    ? ""
    : `Started ${created.toLocaleString()}`;
}
