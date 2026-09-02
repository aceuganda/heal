import { describe, expect, it } from "vitest";

import {
  COLOR_CYCLE_MS,
  DOT_SETTLE_MS,
  DRAW_DURATION_MS,
  HOLD_FRACTION,
  PALETTE,
  PULSE_AMPLITUDE,
  PULSE_FADE_IN_MS,
  SCATTER_MAGNITUDE,
  COLOR_EDGE_DITHER,
  COLOR_SWEEP_SPAN,
  clamp01,
  colorAt,
  colorPhaseOffset,
  dotAlpha,
  dotDelayMs,
  easeOutBack,
  easeOutCubic,
  jitterOffset,
  mix,
  pulseFactor,
  seededUnit,
  settleProgress,
  smoothstep,
  toRgbString,
} from "./dotAnimation";

describe("seededUnit", () => {
  it("is deterministic for the same index and salt", () => {
    expect(seededUnit(42, 1)).toBe(seededUnit(42, 1));
  });

  it("stays within [0, 1)", () => {
    for (let i = 0; i < 200; i++) {
      const v = seededUnit(i);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("gives different dots different values", () => {
    expect(seededUnit(1)).not.toBe(seededUnit(2));
  });

  it("gives one dot independent values across salts", () => {
    // A delay jitter and a scatter angle for the same dot must not move
    // together, or every dot's scatter direction would line up with its
    // arrival order.
    expect(seededUnit(5, 1)).not.toBe(seededUnit(5, 2));
  });
});

describe("easing", () => {
  it("easeOutBack starts at 0 and lands exactly on 1", () => {
    expect(easeOutBack(0)).toBeCloseTo(0, 5);
    expect(easeOutBack(1)).toBeCloseTo(1, 5);
  });

  it("easeOutBack overshoots past 1 before settling", () => {
    const values = Array.from({ length: 20 }, (_, i) => easeOutBack(i / 19));
    expect(Math.max(...values)).toBeGreaterThan(1);
  });

  it("easeOutCubic never overshoots and lands on 1", () => {
    const values = Array.from({ length: 20 }, (_, i) => easeOutCubic(i / 19));
    expect(Math.max(...values)).toBeLessThanOrEqual(1 + 1e-9);
    expect(easeOutCubic(1)).toBeCloseTo(1, 5);
    expect(easeOutCubic(0)).toBeCloseTo(0, 5);
  });

  it("smoothstep is anchored at its ends and midpoint", () => {
    expect(smoothstep(0)).toBe(0);
    expect(smoothstep(1)).toBe(1);
    expect(smoothstep(0.5)).toBeCloseTo(0.5, 5);
  });

  it("clamp01 clamps outside [0, 1]", () => {
    expect(clamp01(-1)).toBe(0);
    expect(clamp01(2)).toBe(1);
    expect(clamp01(0.3)).toBe(0.3);
  });
});

describe("dotDelayMs", () => {
  const COUNT = 170;
  const span = DRAW_DURATION_MS - DOT_SETTLE_MS;

  it("keeps every dot's delay inside the draw window", () => {
    for (let i = 0; i < COUNT; i++) {
      const delay = dotDelayMs(i, COUNT);
      expect(delay).toBeGreaterThanOrEqual(0);
      expect(delay).toBeLessThanOrEqual(span);
    }
  });

  it("guarantees the last dot settles by DRAW_DURATION_MS", () => {
    const last = dotDelayMs(COUNT - 1, COUNT);
    expect(last + DOT_SETTLE_MS).toBeLessThanOrEqual(DRAW_DURATION_MS);
  });

  it("trends later for later indices despite jitter", () => {
    // Not strictly monotonic (that's the point of the jitter), but the
    // first dot should start well before the last one.
    expect(dotDelayMs(0, COUNT)).toBeLessThan(dotDelayMs(COUNT - 1, COUNT));
  });

  it("puts everything at 0 for a single dot", () => {
    expect(dotDelayMs(0, 1)).toBe(0);
  });
});

describe("jitterOffset", () => {
  it("stays within SCATTER_MAGNITUDE in every direction", () => {
    for (let i = 0; i < 170; i++) {
      const [dx, dy] = jitterOffset(i);
      const radius = Math.hypot(dx, dy);
      expect(radius).toBeLessThanOrEqual(SCATTER_MAGNITUDE + 1e-9);
    }
  });

  it("is deterministic", () => {
    expect(jitterOffset(17)).toEqual(jitterOffset(17));
  });
});

describe("settleProgress", () => {
  it("is 0 before the dot's delay", () => {
    expect(settleProgress(0, 100)).toBe(0);
  });

  it("reaches exactly 1 at the end of the settle window", () => {
    expect(settleProgress(360, 100)).toBeCloseTo(1, 5); // delay 100 + DOT_SETTLE_MS 260
  });

  it("overshoots partway through", () => {
    const mid = settleProgress(100 + DOT_SETTLE_MS * 0.85, 100);
    expect(mid).toBeGreaterThan(1);
  });
});

describe("dotAlpha", () => {
  it("is 0 at or before the delay", () => {
    expect(dotAlpha(100, 100)).toBe(0);
    expect(dotAlpha(50, 100)).toBe(0);
  });

  it("reaches 1 once settled and never overshoots", () => {
    expect(dotAlpha(100 + DOT_SETTLE_MS, 100)).toBeCloseTo(1, 5);
    for (let t = 0; t <= DOT_SETTLE_MS; t += 20) {
      expect(dotAlpha(100 + t, 100)).toBeLessThanOrEqual(1 + 1e-9);
    }
  });
});

describe("pulseFactor", () => {
  const delay = 0;
  const settledAt = delay + DOT_SETTLE_MS;

  it("is exactly 1 before the dot has settled", () => {
    expect(pulseFactor(settledAt - 1, delay, 0.5, 0.5)).toBe(1);
  });

  it("is exactly 1 the instant settling finishes (fade-in starts at 0)", () => {
    expect(pulseFactor(settledAt, delay, 0.5, 0.5)).toBeCloseTo(1, 5);
  });

  it("stays within amplitude once fully faded in", () => {
    const afterFadeIn = settledAt + PULSE_FADE_IN_MS + 10;
    for (let x = 0; x <= 1; x += 0.25) {
      const factor = pulseFactor(afterFadeIn, delay, x, x);
      expect(factor).toBeGreaterThanOrEqual(1 - PULSE_AMPLITUDE - 1e-9);
      expect(factor).toBeLessThanOrEqual(1 + PULSE_AMPLITUDE + 1e-9);
    }
  });
});

describe("mix", () => {
  it("returns the first colour at t=0 and the second at t=1", () => {
    const a: readonly [number, number, number] = [10, 20, 30];
    const b: readonly [number, number, number] = [110, 120, 130];
    expect(mix(a, b, 0)).toEqual(a);
    expect(mix(a, b, 1)).toEqual(b);
    expect(mix(a, b, 0.5)).toEqual([60, 70, 80]);
  });
});

describe("colorAt", () => {
  it("is a clean palette colour at the very start of its cycle", () => {
    expect(colorAt(0, 0)).toEqual(PALETTE[0].color);
  });

  it("holds that colour through HOLD_FRACTION of the first stop's dwell", () => {
    const holdEnd = PALETTE[0].weight * HOLD_FRACTION * COLOR_CYCLE_MS;
    expect(colorAt(0, holdEnd * 0.99)).toEqual(PALETTE[0].color);
  });

  it("is periodic across COLOR_CYCLE_MS", () => {
    expect(colorAt(0.3, 777)).toEqual(colorAt(0.3, 777 + COLOR_CYCLE_MS));
  });

  it("gives two different seeds different phases at the same instant", () => {
    expect(colorAt(0, 0)).not.toEqual(colorAt(0.5, 0));
  });

  it("never produces a channel outside any palette colour's range", () => {
    const channels = PALETTE.map((s) => s.color);
    const mins = [0, 1, 2].map((c) => Math.min(...channels.map((rgb) => rgb[c])));
    const maxs = [0, 1, 2].map((c) => Math.max(...channels.map((rgb) => rgb[c])));
    for (let t = 0; t < COLOR_CYCLE_MS; t += 137) {
      const color = colorAt(0.17, t);
      color.forEach((v, c) => {
        expect(v).toBeGreaterThanOrEqual(mins[c] - 1e-6);
        expect(v).toBeLessThanOrEqual(maxs[c] + 1e-6);
      });
    }
  });
});

describe("toRgbString", () => {
  it("rounds and formats as an rgb() string", () => {
    expect(toRgbString([15.4, 118.6, 109.5])).toBe("rgb(15, 119, 110)");
  });
});

describe("colorPhaseOffset", () => {
  it("gives neighbouring dots nearly the same phase", () => {
    // The property that makes the palette read as a band sweeping across the
    // mark rather than as speckle: two dots a grid step apart must not land
    // on different palette colours.
    const a = colorPhaseOffset(0.4, 0.4, 0.5);
    const b = colorPhaseOffset(0.44, 0.4, 0.5);
    expect(Math.abs(a - b)).toBeLessThan(0.05);
  });

  it("separates opposite corners by most of the sweep span", () => {
    const northWest = colorPhaseOffset(0, 0, 0.5);
    const southEast = colorPhaseOffset(1, 1, 0.5);
    expect(Math.abs(northWest - southEast)).toBeCloseTo(2 * COLOR_SWEEP_SPAN, 6);
  });

  it("keeps the per-dot dither small enough not to break the band", () => {
    // Two dots in the same place, different seeds: the whole spread available
    // to the dither has to stay inside one dither width.
    const low = colorPhaseOffset(0.5, 0.5, 0);
    const high = colorPhaseOffset(0.5, 0.5, 1);
    expect(Math.abs(high - low)).toBeCloseTo(COLOR_EDGE_DITHER, 6);
  });

  it("puts the band's leading edge at the north-west", () => {
    // Negated on purpose: the colour should travel with the draw, down across
    // the continent, not climb back up against it.
    expect(colorPhaseOffset(0.9, 0.9, 0.5)).toBeLessThan(
      colorPhaseOffset(0.1, 0.1, 0.5)
    );
  });
});
