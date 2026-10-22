/**
 * Tests for the change-password form's rules. They must match the server's,
 * or the form either blocks a password the server would take or sends one it
 * will refuse with a less helpful message.
 */
import { describe, expect, it } from "vitest";

import { detailOf, passwordProblem, signedOutMessage } from "./password";

const EMAIL = "Admin@heal.test";
const ok = {
  current: "first-boot-pass",
  next: "clinic-rota-42",
  confirm: "clinic-rota-42",
};

describe("passwordProblem", () => {
  it("accepts a reasonable change", () => {
    expect(passwordProblem(ok, EMAIL)).toBeNull();
  });

  it.each([
    [{ ...ok, current: "" }, "current password"],
    [{ ...ok, next: "short", confirm: "short" }, "at least 8"],
    [{ ...ok, next: ok.current, confirm: ok.current }, "different"],
    [{ ...ok, next: "Password", confirm: "Password" }, "easy to guess"],
    [
      { ...ok, next: "admin@heal.test", confirm: "admin@heal.test" },
      "easy to guess",
    ],
    [{ ...ok, confirm: "clinic-rota-43" }, "do not match"],
  ])("refuses %o", (change, reason) => {
    expect(passwordProblem(change, EMAIL)).toContain(reason);
  });
});

describe("detailOf", () => {
  it("reads a string detail", () => {
    expect(
      detailOf({ detail: "The current password is not correct." }, "x")
    ).toBe("The current password is not correct.");
  });

  it("reads the first validation message", () => {
    expect(detailOf({ detail: [{ msg: "field required" }] }, "x")).toBe(
      "field required"
    );
  });

  it("falls back on anything else", () => {
    expect(detailOf(null, "Could not change it")).toBe("Could not change it");
  });
});

describe("signedOutMessage", () => {
  it.each([
    [0, "Password changed."],
    [1, "Password changed. 1 other session signed out."],
    [3, "Password changed. 3 other sessions signed out."],
  ])("%i", (count, message) => {
    expect(signedOutMessage(count)).toBe(message);
  });
});
