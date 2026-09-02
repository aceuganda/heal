/**
 * Tests for the external-reference publisher catalogue.
 *
 * Two things must not go wrong here. A reference must never be matched to the
 * wrong body — pointing a health worker at NICE's UK guidance when the answer
 * named Uganda's national protocol is worse than pointing them nowhere. And a
 * name Heal does not recognise must resolve to nothing at all, because the
 * alternative is a guessed link, which is the one thing the external-reference
 * design exists to prevent.
 */
import { describe, expect, it } from "vitest";

import { lookupPublisher, publisherHost } from "./externalSources";

describe("lookupPublisher", () => {
  it("has nothing to say about an empty name", () => {
    expect(lookupPublisher("")).toBeNull();
    expect(lookupPublisher(null)).toBeNull();
    expect(lookupPublisher(undefined)).toBeNull();
  });

  it("returns nothing for a body it has not been taught", () => {
    expect(lookupPublisher("The Lancet")).toBeNull();
    expect(lookupPublisher("Harrison's Principles of Internal Medicine")).toBeNull();
    expect(lookupPublisher("a colleague at the district hospital")).toBeNull();
  });

  it("recognises the bodies the safety prompt actually names", () => {
    expect(lookupPublisher("WHO")?.name).toBe("World Health Organization");
    expect(lookupPublisher("World Health Organization")?.name).toBe(
      "World Health Organization"
    );
    expect(lookupPublisher("CDC")?.name).toBe(
      "US Centers for Disease Control and Prevention"
    );
    expect(lookupPublisher("Uganda Clinical Guidelines")?.name).toBe(
      "Uganda Ministry of Health"
    );
  });

  it("reads a name the way the model actually writes one", () => {
    // `external_refs.py` keeps the model's whole line: "[1] WHO -- Yellow
    // fever fact sheet" arrives here as everything after the marker.
    expect(lookupPublisher("WHO — Yellow fever fact sheet")?.name).toBe(
      "World Health Organization"
    );
    expect(
      lookupPublisher("Uganda Clinical Guidelines 2023, section 3.1")?.name
    ).toBe("Uganda Ministry of Health");
  });

  it("prefers the national body when a name cites both", () => {
    // The guideline that applies in the room beats the one it was derived
    // from.
    expect(lookupPublisher("Uganda Clinical Guidelines (WHO-aligned)")?.name).toBe(
      "Uganda Ministry of Health"
    );
  });

  it("does not match an acronym hiding inside an ordinary word", () => {
    expect(lookupPublisher("Whole blood transfusion handbook")).toBeNull();
  });

  it("does not mistake the English words 'who' and 'nice' for the bodies", () => {
    expect(lookupPublisher("Guidance for staff who manage TB")).toBeNull();
    expect(lookupPublisher("A nice summary of paediatric dosing")).toBeNull();
    // Still found when actually cited, in either the acronym or the full name.
    expect(lookupPublisher("WHO guidance for staff who manage TB")?.name).toBe(
      "World Health Organization"
    );
    expect(lookupPublisher("world health organisation")?.name).toBe(
      "World Health Organization"
    );
  });

  it("points at a library, never at a document", () => {
    // A deep link would be a claim that a specific page says what the answer
    // said. Nobody fetched it, so the link stops at the front door.
    for (const name of ["WHO", "CDC", "Uganda Clinical Guidelines", "UNAIDS", "UNICEF", "NICE"]) {
      const publisher = lookupPublisher(name);
      expect(publisher).not.toBeNull();
      expect(publisher!.url).toMatch(/^https:\/\//);
      expect(publisher!.url).not.toMatch(/\.pdf$/i);
    }
  });

  it("tells the reader what they still have to do", () => {
    const publisher = lookupPublisher("WHO")!;
    expect(publisher.about.length).toBeGreaterThan(0);
    expect(publisher.findIt.length).toBeGreaterThan(0);
  });
});

describe("publisherHost", () => {
  it("shows where a link goes, without the scheme or path", () => {
    expect(publisherHost(lookupPublisher("WHO")!)).toBe("www.who.int");
    expect(publisherHost(lookupPublisher("Uganda Clinical Guidelines")!)).toBe(
      "www.health.go.ug"
    );
  });
});
