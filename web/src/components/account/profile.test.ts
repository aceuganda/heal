import { describe, expect, it } from "vitest";
import { profileProblem, signupErrorMessage } from "./profile";

const SEX = {
  female: "Female",
  male: "Male",
  prefer_not_to_say: "Prefer not to say",
};
const TODAY = new Date(2026, 9, 22);

function problem(
  over: Partial<{
    organisation: string;
    date_of_birth: string;
    sex: string;
  }> = {}
) {
  return profileProblem(
    {
      organisation: "Mulago Hospital",
      date_of_birth: "1990-05-01",
      sex: "female",
      ...over,
    },
    SEX,
    TODAY
  );
}

describe("profileProblem", () => {
  it("accepts a complete profile", () => {
    expect(problem()).toBeNull();
  });

  it("needs an organisation", () => {
    expect(problem({ organisation: "  " })).toMatch(/organisation/);
  });

  it("needs a date of birth", () => {
    expect(problem({ date_of_birth: "" })).toMatch(/date of birth/);
  });

  it("refuses a future date", () => {
    expect(problem({ date_of_birth: "2030-01-01" })).toBe(
      "Enter a real date of birth."
    );
  });

  it("counts the sixteenth birthday on the day, like the server", () => {
    expect(problem({ date_of_birth: "2010-10-22" })).toBeNull();
    expect(problem({ date_of_birth: "2010-10-23" })).toMatch(/16/);
  });

  it("needs a sex option", () => {
    expect(problem({ sex: "" })).toMatch(/sex/);
  });
});

describe("signupErrorMessage", () => {
  it("names a taken email", () => {
    expect(
      signupErrorMessage({ detail: "REGISTER_USER_ALREADY_EXISTS" })
    ).toMatch(/already exists/);
  });

  it("shows the profile rule's sentence from a 422", () => {
    const body = {
      detail: [{ msg: "Value error, Enter a real date of birth." }],
    };
    expect(signupErrorMessage(body)).toBe("Enter a real date of birth.");
  });

  it("falls back when the body is unreadable", () => {
    expect(signupErrorMessage(null)).toBe("Unknown error");
  });
});
