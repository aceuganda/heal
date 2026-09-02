/**
 * Tests for the playground's pure logic.
 *
 * Two things must not go wrong on this screen. It must not claim a run used
 * the defaults when a knob was moved, and it must not draw the score floor in
 * the wrong place — an admin reads "cut by 0.01" off that line and changes a
 * clinical-safety parameter on the strength of it.
 */
import { describe, expect, it } from "vitest";

import {
  appliedFloor,
  changedNames,
  Candidate,
  floorLineAfter,
  formatMs,
  formatScore,
  isOverridden,
  isSaveable,
  overridesFor,
  savePayload,
  PlaygroundResult,
  shortfall,
  TunableValues,
} from "./lib";

const defaults: TunableValues = {
  min_retrieval_score: 0.35,
  hybrid_alpha: 0.6,
  hybrid_search: true,
  retrieval_top_k: 20,
  context_top_k: 5,
  max_chunks_per_source: 2,
  temperature: 0,
  max_output_tokens: 1024,
  top_p: 1,
  verbosity: "standard",
};

const candidate = (over: Partial<Candidate> = {}): Candidate => ({
  index: 1,
  source_id: "src-1",
  title: "Uganda ART Guidelines",
  version: "2022",
  ordinal: 0,
  text: "Give TDF/3TC/DTG once daily.",
  truncated: false,
  dense_score: 0.8,
  sparse_score: 0,
  score: 0.8,
  passed_floor: true,
  survived_cap: true,
  in_context: true,
  citation_number: 1,
  ...over,
});

describe("isOverridden", () => {
  it("treats an untouched value as the default", () => {
    expect(isOverridden(0.35, 0.35)).toBe(false);
  });

  it("ignores floating-point noise from a slider", () => {
    // 0.1 + 0.2 is 0.30000000000000004; a strict compare would call an
    // untouched slider "overridden" and light up the warning banner.
    expect(isOverridden(0.1 + 0.2, 0.3)).toBe(false);
  });

  it("notices a value a hundredth away from the default", () => {
    expect(isOverridden(0.36, 0.35)).toBe(true);
  });

  it("compares booleans without arithmetic", () => {
    expect(isOverridden(false, true)).toBe(true);
    expect(isOverridden(true, true)).toBe(false);
  });
});

describe("changedNames", () => {
  it("is empty when nothing was moved", () => {
    expect(changedNames({ ...defaults }, defaults)).toEqual([]);
  });

  it("names only the knobs that differ", () => {
    expect(
      changedNames(
        { ...defaults, min_retrieval_score: 0.2, hybrid_search: false },
        defaults
      )
    ).toEqual(["min_retrieval_score", "hybrid_search"]);
  });

  it("always reports in the declared order, not the order they were touched", () => {
    expect(
      changedNames(
        { ...defaults, context_top_k: 9, hybrid_alpha: 0.1 },
        defaults
      )
    ).toEqual(["hybrid_alpha", "context_top_k"]);
  });
});

describe("overridesFor", () => {
  it("sends nothing when the form is on the defaults", () => {
    // Sending all six would have the server report every one as overridden,
    // and the screen would then warn about a run that used the defaults.
    expect(overridesFor({ ...defaults }, defaults)).toEqual({});
  });

  it("sends only the moved knobs", () => {
    expect(
      overridesFor({ ...defaults, retrieval_top_k: 40 }, defaults)
    ).toEqual({ retrieval_top_k: 40 });
  });

  it("sends a switched-off boolean rather than dropping it as falsy", () => {
    expect(
      overridesFor({ ...defaults, hybrid_search: false }, defaults)
    ).toEqual({ hybrid_search: false });
  });

  it("sends a zero rather than dropping it as falsy", () => {
    expect(
      overridesFor({ ...defaults, min_retrieval_score: 0 }, defaults)
    ).toEqual({ min_retrieval_score: 0 });
  });
});

describe("floorLineAfter", () => {
  it("puts the line between the last pass and the first failure", () => {
    const list = [
      candidate({ index: 1, passed_floor: true }),
      candidate({ index: 2, passed_floor: true }),
      candidate({ index: 3, passed_floor: false }),
    ];
    expect(floorLineAfter(list)).toBe(2);
  });

  it("draws no line when every candidate cleared the floor", () => {
    expect(floorLineAfter([candidate(), candidate({ index: 2 })])).toBeNull();
  });

  it("draws no line when the floor rejected everything", () => {
    expect(floorLineAfter([candidate({ passed_floor: false })])).toBeNull();
  });

  it("draws no line on an empty result", () => {
    expect(floorLineAfter([])).toBeNull();
  });
});

describe("shortfall", () => {
  it("says how far under the floor a rejected candidate fell", () => {
    const near = candidate({ score: 0.34, passed_floor: false });
    expect(shortfall(near, 0.35)).toBeCloseTo(0.01, 6);
  });

  it("is null for a candidate that passed", () => {
    expect(shortfall(candidate({ score: 0.8 }), 0.35)).toBeNull();
  });
});

describe("appliedFloor", () => {
  it("reads the floor the run used, not the one the controls now show", () => {
    // The admin moves a slider after a run. The list on screen belongs to the
    // old run, so the line has to be drawn at the old floor.
    const result = {
      settings: [
        { name: "hybrid_alpha", value: 0.6, default: 0.6, overridden: false, clamped: false, requested: null },
        { name: "min_retrieval_score", value: 0.2, default: 0.35, overridden: true, clamped: false, requested: 0.2 },
      ],
    } as PlaygroundResult;
    expect(appliedFloor(result)).toBe(0.2);
  });

  it("falls back to zero rather than guessing when the knob is absent", () => {
    expect(appliedFloor({ settings: [] } as unknown as PlaygroundResult)).toBe(0);
  });
});

describe("formatting", () => {
  it("shows scores at the precision the API rounds to", () => {
    expect(formatScore(0.3)).toBe("0.3000");
  });

  it("keeps sub-second timings in milliseconds", () => {
    expect(formatMs(430)).toBe("430 ms");
  });

  it("switches to seconds once a stage is slow enough to notice", () => {
    expect(formatMs(2400)).toBe("2.4 s");
  });
});

describe("savePayload", () => {
  it("sends nothing when nothing was moved", () => {
    // An empty save would still write a row and pin every knob, which is how
    // a deployment stops following its own environment by accident.
    expect(savePayload(defaults, defaults, "", "")).toEqual({});
  });

  it("sends only the wording knobs that changed", () => {
    const body = savePayload(
      { ...defaults, temperature: 0.4, min_retrieval_score: 0.9 },
      defaults,
      "",
      ""
    );
    expect(body).toEqual({ temperature: 0.4 });
  });

  it("never offers to save a retrieval knob", () => {
    // The score floor decides whether a dose may be quoted at all. It is set
    // from measured results, in the environment, not from a save button.
    const body = savePayload(
      { ...defaults, min_retrieval_score: 0.9, context_top_k: 9 },
      defaults,
      "",
      ""
    );
    expect(body).toEqual({});
  });

  it("carries a chosen model", () => {
    expect(savePayload(defaults, defaults, "gpt-4o", "")).toEqual({
      chat_model: "gpt-4o",
    });
  });

  it("treats the empty model picker as 'leave it alone'", () => {
    expect(savePayload(defaults, defaults, "", "")).not.toHaveProperty(
      "chat_model"
    );
  });

  it("carries a verbosity level", () => {
    expect(
      savePayload({ ...defaults, verbosity: "brief" }, defaults, "", "")
    ).toEqual({ verbosity: "brief" });
  });
});

describe("isSaveable", () => {
  it("allows the wording knobs", () => {
    expect(isSaveable("temperature")).toBe(true);
    expect(isSaveable("verbosity")).toBe(true);
  });

  it("refuses the retrieval knobs", () => {
    expect(isSaveable("min_retrieval_score")).toBe(false);
    expect(isSaveable("hybrid_alpha")).toBe(false);
  });
});
