import { describe, expect, it } from "vitest";
import { avatarLook } from "./gradient";

describe("avatarLook", () => {
  it("uses the email's first letter, upper-cased", () => {
    expect(avatarLook("khalifa@example.org").initial).toBe("K");
  });

  it("is stable for one person", () => {
    expect(avatarLook("a@b.org")).toEqual(avatarLook(" A@B.org "));
  });

  it("usually differs between people", () => {
    const looks = new Set(
      ["a@x.org", "b@x.org", "c@x.org", "d@x.org", "e@x.org"].map(
        (e) => avatarLook(e).background
      )
    );
    expect(looks.size).toBeGreaterThan(3);
  });

  it("stays in the reddish band", () => {
    for (const email of ["a@x.org", "zz@y.org", "nurse1@clinic.ug", "q"]) {
      const hue = Number(avatarLook(email).background.match(/hsl\((\d+)/)![1]);
      expect(hue >= 340 || hue <= 25).toBe(true);
    }
  });

  it("falls back to a question mark with no email", () => {
    expect(avatarLook(null).initial).toBe("?");
  });
});
