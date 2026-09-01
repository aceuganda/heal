/**
 * Tests for rewriting `[1]` markers into openable links.
 *
 * These mirror `backend/tests/unit/heal/chat/test_citations.py`. The two
 * regexes have to agree: a marker the frontend linkifies but the backend never
 * stored is a link to nothing, and one the backend stored but the frontend
 * leaves alone is a citation the reader cannot open.
 */
import { describe, expect, it } from "vitest";

import {
  citationHref,
  citationKeyFromHref,
  linkifyCitations,
} from "./citationMarkers";

const keys = (...markers: string[]) => new Set(markers);

describe("linkifyCitations", () => {
  it("rewrites a marker that has a source behind it", () => {
    expect(linkifyCitations("Give TDF/3TC/DTG daily [1].", keys("1"))).toBe(
      "Give TDF/3TC/DTG daily [1](#heal-citation-1)."
    );
  });

  it("rewrites every occurrence of a repeated marker", () => {
    expect(linkifyCitations("[1] and again [1]", keys("1"))).toBe(
      "[1](#heal-citation-1) and again [1](#heal-citation-1)"
    );
  });

  it("rewrites two-digit markers", () => {
    expect(linkifyCitations("see [12]", keys("12"))).toBe(
      "see [12](#heal-citation-12)"
    );
  });

  it("treats [01] as citation 1, the way the backend's int() does", () => {
    expect(linkifyCitations("see [01]", keys("1"))).toBe(
      "see [1](#heal-citation-1)"
    );
  });

  it("returns the answer untouched when nothing was cited", () => {
    const answer = "Take one tablet daily [1].";
    expect(linkifyCitations(answer, keys())).toBe(answer);
  });
});

describe("what must not be rewritten", () => {
  /** An over-eager rewrite corrupts the answer a health worker reads. */

  it("leaves a marker with no stored source as plain text", () => {
    // The model invents [9] when it was handed five passages. The backend
    // drops it; the reader must not get a link to nothing.
    expect(linkifyCitations("dose [1] and [9]", keys("1"))).toBe(
      "dose [1](#heal-citation-1) and [9]"
    );
  });

  it("leaves a markdown link alone", () => {
    const answer = "see [1](https://example.org/guide)";
    expect(linkifyCitations(answer, keys("1"))).toBe(answer);
  });

  it("leaves bracketed words alone", () => {
    const answer = "[see below] and [note]";
    expect(linkifyCitations(answer, keys("1"))).toBe(answer);
  });

  it("leaves an unclosed bracket alone", () => {
    const answer = "the dose [1 is unclear";
    expect(linkifyCitations(answer, keys("1"))).toBe(answer);
  });

  it("leaves a marker inside an inline code span alone", () => {
    const answer = "the literal `array[1]` is not a citation";
    expect(linkifyCitations(answer, keys("1"))).toBe(answer);
  });

  it("leaves a marker inside a fenced block alone", () => {
    const answer = "before [1]\n```\nrow[1] = 2\n```\nafter [1]";
    expect(linkifyCitations(answer, keys("1"))).toBe(
      "before [1](#heal-citation-1)\n```\nrow[1] = 2\n```\nafter [1](#heal-citation-1)"
    );
  });
});

describe("citationKeyFromHref", () => {
  it("recovers the marker from a rewritten link", () => {
    expect(citationKeyFromHref(citationHref("3"))).toBe("3");
  });

  it("returns null for a real link, so it renders as a link", () => {
    expect(citationKeyFromHref("https://example.org")).toBeNull();
  });

  it("returns null for a missing href", () => {
    expect(citationKeyFromHref(undefined)).toBeNull();
  });
});
