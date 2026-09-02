/**
 * Tests for how the chat sidebar dates and orders past sessions.
 *
 * The bug these exist to keep out: the previous grouping divided a raw
 * millisecond span by a day and called anything under 1 "Today", so a chat
 * started at 23:50 last night appeared under Today for the whole of the
 * following morning. Every boundary here is a calendar boundary, and `now` is
 * injected so the boundary can actually be stood on.
 */
import { describe, expect, it } from "vitest";

import { ChatSession } from "../interfaces";
import {
  formatSessionStart,
  fullSessionStart,
  groupForSession,
  groupSessionsByDateRange,
  SESSION_GROUPS,
} from "./sessionGrouping";

// A Wednesday, mid-afternoon, in local time.
const NOW = new Date(2026, 8, 2, 14, 30);

const at = (
  year: number,
  month: number,
  day: number,
  hour = 12,
  minute = 0
): string => new Date(year, month, day, hour, minute).toISOString();

const session = (id: string, timeCreated: string): ChatSession => ({
  id,
  name: id,
  persona_id: 0,
  time_created: timeCreated,
});

describe("groupForSession", () => {
  it("files this morning and this afternoon under Today", () => {
    expect(groupForSession(at(2026, 8, 2, 0, 1), NOW)).toBe("Today");
    expect(groupForSession(at(2026, 8, 2, 14, 29), NOW)).toBe("Today");
  });

  it("does not call last night Today", () => {
    // The whole point. Twenty minutes before midnight is yesterday, however
    // few hours ago it was.
    expect(groupForSession(at(2026, 8, 1, 23, 50), NOW)).toBe("Yesterday");
  });

  it("counts the week and the month by calendar days", () => {
    expect(groupForSession(at(2026, 7, 31), NOW)).toBe("Previous 7 days"); // 2 days
    expect(groupForSession(at(2026, 7, 26), NOW)).toBe("Previous 7 days"); // 7 days
    expect(groupForSession(at(2026, 7, 25), NOW)).toBe("Previous 30 days"); // 8 days
    expect(groupForSession(at(2026, 7, 3), NOW)).toBe("Previous 30 days"); // 30 days
    expect(groupForSession(at(2026, 7, 2), NOW)).toBe("Older"); // 31 days
  });

  it("treats a future timestamp as today rather than hiding it", () => {
    // Clock skew between the server and the device, not a scheduled chat.
    expect(groupForSession(at(2026, 8, 5), NOW)).toBe("Today");
  });

  it("keeps an undatable session reachable", () => {
    expect(groupForSession("not a date", NOW)).toBe("Older");
  });
});

describe("groupSessionsByDateRange", () => {
  it("returns every group, so headings render in a fixed order", () => {
    const groups = groupSessionsByDateRange([], NOW);
    expect(Object.keys(groups)).toEqual([...SESSION_GROUPS]);
  });

  it("orders newest first inside a group, whatever order the API gave", () => {
    const morning = session("morning", at(2026, 8, 2, 9, 0));
    const afternoon = session("afternoon", at(2026, 8, 2, 13, 0));
    const lunchtime = session("lunchtime", at(2026, 8, 2, 12, 0));

    const groups = groupSessionsByDateRange(
      [morning, afternoon, lunchtime],
      NOW
    );
    expect(groups.Today.map((s) => s.id)).toEqual([
      "afternoon",
      "lunchtime",
      "morning",
    ]);
  });

  it("puts each session in exactly one group", () => {
    const sessions = [
      session("today", at(2026, 8, 2, 9, 0)),
      session("yesterday", at(2026, 8, 1, 23, 50)),
      session("last week", at(2026, 7, 28)),
      session("last month", at(2026, 7, 10)),
      session("ancient", at(2025, 11, 1)),
    ];
    const groups = groupSessionsByDateRange(sessions, NOW);
    const total = SESSION_GROUPS.reduce(
      (sum, group) => sum + groups[group].length,
      0
    );
    expect(total).toBe(sessions.length);
    expect(groups.Today.map((s) => s.id)).toEqual(["today"]);
    expect(groups.Yesterday.map((s) => s.id)).toEqual(["yesterday"]);
    expect(groups["Previous 7 days"].map((s) => s.id)).toEqual(["last week"]);
    expect(groups["Previous 30 days"].map((s) => s.id)).toEqual(["last month"]);
    expect(groups.Older.map((s) => s.id)).toEqual(["ancient"]);
  });
});

describe("formatSessionStart", () => {
  it("shows only the clock for a session started today", () => {
    // Under a "Today" heading, the date would be noise.
    const formatted = formatSessionStart(at(2026, 8, 2, 9, 5), NOW);
    expect(formatted).toMatch(/^\d{1,2}[:.]\d{2}/);
    expect(formatted).not.toMatch(/Sep/);
  });

  it("names yesterday and still gives the time", () => {
    expect(formatSessionStart(at(2026, 8, 1, 23, 50), NOW)).toMatch(
      /^Yesterday \d{1,2}[:.]\d{2}/
    );
  });

  it("drops the clock once a date is what matters", () => {
    const formatted = formatSessionStart(at(2026, 7, 28, 9, 5), NOW);
    expect(formatted).toMatch(/28/);
    expect(formatted).not.toMatch(/09[:.]05/);
  });

  it("adds the year only when it is in doubt", () => {
    expect(formatSessionStart(at(2026, 7, 10), NOW)).not.toMatch(/2026/);
    expect(formatSessionStart(at(2025, 11, 1), NOW)).toMatch(/2025/);
  });

  it("renders nothing rather than 'Invalid Date' under a clinical chat", () => {
    expect(formatSessionStart("not a date", NOW)).toBe("");
    expect(fullSessionStart("not a date")).toBe("");
  });
});
