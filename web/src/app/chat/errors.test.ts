import { describe, expect, it } from "vitest";
import { ChatRequestError, chatErrorMessage, errorDetail } from "./errors";

describe("errorDetail", () => {
  it("reads the server's detail", async () => {
    const response = new Response(
      JSON.stringify({ detail: "Translation is down." }),
      {
        status: 503,
      }
    );
    expect(await errorDetail(response, "fallback")).toBe(
      "Translation is down."
    );
  });

  it("falls back on a plain-text body instead of throwing", async () => {
    // The original bug: "Internal Server Error" fed to JSON.parse.
    const response = new Response("Internal Server Error", { status: 500 });
    expect(await errorDetail(response, "fallback")).toBe("fallback");
  });

  it("falls back when the JSON has nothing to show", async () => {
    const response = new Response(JSON.stringify({}), { status: 500 });
    expect(await errorDetail(response, "fallback")).toBe("fallback");
  });
});

describe("chatErrorMessage", () => {
  it("passes through a message the server already worded", () => {
    expect(chatErrorMessage(new ChatRequestError("Try later."), false)).toBe(
      "Try later."
    );
  });

  it("says the answer may be saved when the stream was cut off", () => {
    expect(chatErrorMessage(new TypeError("network error"), true)).toMatch(
      /interrupted.*Refresh/
    );
  });

  it("says Heal could not be reached before anything arrived", () => {
    expect(chatErrorMessage(new TypeError("Failed to fetch"), false)).toMatch(
      /Couldn't reach Heal/
    );
  });

  it("never shows a raw parser error", () => {
    const parse = new SyntaxError("Unexpected token 'I'");
    expect(chatErrorMessage(parse, false)).not.toMatch(/Unexpected token/);
  });
});
