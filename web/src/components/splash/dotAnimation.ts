/**
 * Pure timing, easing and colour logic for the splash mark's dot-draw.
 *
 * Kept apart from the canvas component so the schedule and palette math can be
 * verified without a DOM: a stagger that overruns its budget or a colour that
 * drifts off-palette is a one-line assertion here, not something that has to
 * be eyeballed on a screen that is only up for a second and a half.
 *
 * Everything below is a function of `(index, elapsedMs)`. There is no mutable
 * per-dot state and no `Math.random()` — the component recomputes a dot's pose
 * from scratch every frame, and the pseudo-randomness is a deterministic hash
 * of the dot's own index so the same mark draws the same way on every visit.
 */

/** Every dot has arrived and is sitting at its true position by this point.
 *  The splash starts leaving at `SPLASH_HOLD_MS` (AppSplashScreen), so this
 *  leaves a long hold before that — the draw must never still be running when
 *  the fade begins, and the assembled mark is the part worth looking at. */
export const DRAW_DURATION_MS = 780;

/** How long one dot's own pop-in takes, from first appearing to settled. */
export const DOT_SETTLE_MS = 260;

/** How far a dot starts displaced from its true position, in the same
 *  normalised units as `AFRICA_DOTS`. Large enough to read as scatter,
 *  small enough that the mark is still recognisably assembling itself
 *  rather than dots flying in from off-screen. */
export const SCATTER_MAGNITUDE = 0.055;

/** Softens the handoff from a dot's settle into the ambient pulse, so the
 *  pulse fades up rather than switching on the instant settle hits 1. */
export const PULSE_FADE_IN_MS = 220;

/** One full traveling-wave cycle. Only a slice of it is ever seen — the
 *  splash is gone before this loops — so this only has to feel unhurried,
 *  not actually repeat cleanly. */
export const PULSE_PERIOD_MS = 1500;

/** Scale swing from the pulse. Kept low deliberately: the brief asked for
 *  something that reads as breathing, and anything much above this starts
 *  reading as blinking instead. */
export const PULSE_AMPLITUDE = 0.07;

/** Wave crests across the mark's diagonal at once. Just over one, so the
 *  pulse reads as a single band of emphasis moving through, not ripples. */
export const PULSE_WAVE_DENSITY = 1.1;

/** One full loop through the palette. As with the pulse period, only the
 *  opening slice plays before the splash unmounts. */
export const COLOR_CYCLE_MS = 5200;

/** How much of the palette is laid across the mark at once, as a fraction of
 *  the cycle per unit of the north-west to south-east diagonal.
 *
 *  This is what makes the colour a WAVE rather than confetti. Give each dot
 *  an unrelated phase and all four colours land next to each other in every
 *  square inch: the mark stops reading as a logo and starts reading as
 *  speckle. Deriving the phase from position instead means neighbours share a
 *  colour and the palette sweeps across the continent as a band. */
export const COLOR_SWEEP_SPAN = 0.42;

/** A little per-dot phase noise on top of the sweep, to dither the boundary
 *  between two colour bands. Without it the bands meet along a hard diagonal
 *  line, which at this dot size looks like a rendering seam; with it the
 *  colours interleave for a dot or two and the edge reads as soft. Small
 *  enough that it never breaks the band into speckle. */
export const COLOR_EDGE_DITHER = 0.035;

/** Fraction of a palette stop's dwell spent holding that colour outright
 *  before easing into the next one. Below this, a dot is simply red (or
 *  black, or...); above it, it is blending.
 *
 *  Deliberately high, and it has to rise as the accent weights fall. The
 *  blend is a fraction of the stop being LEFT, so a near-zero accent stop
 *  with a low hold would never once show its own colour — it would be a
 *  smear from red to red by way of something muddy. At 0.78 an accent that
 *  dwells for 4% of the cycle is still itself for three-quarters of that,
 *  which is what makes it read as a fast flicker of colour rather than as
 *  dirt on the red. */
export const HOLD_FRACTION = 0.78;

export function clamp01(t: number): number {
  return Math.min(1, Math.max(0, t));
}

/**
 * A deterministic pseudo-random value in [0, 1) for a given index.
 *
 * `salt` lets one dot draw more than one independent value (a delay jitter
 * and a scatter angle should not correlate with each other) without a second
 * lookup table. This is a bit-mixing hash, not a cryptographic one — it only
 * has to look unpatterned across 170 small integers.
 */
export function seededUnit(index: number, salt = 0): number {
  let h = (Math.imul(index, 374761393) + Math.imul(salt, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h = (h ^ (h >>> 16)) >>> 0;
  return h / 4294967296;
}

/** Overshoots past 1 before settling back to exactly 1 at t=1 — that
 *  overshoot is what gives a dot's arrival its "loose" feel instead of a
 *  rigid snap into place. Standard Penner back-ease. */
export function easeOutBack(t: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  const x = clamp01(t) - 1;
  return 1 + c3 * x * x * x + c1 * x * x;
}

export function easeOutCubic(t: number): number {
  const x = 1 - clamp01(t);
  return 1 - x * x * x;
}

export function smoothstep(t: number): number {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

/**
 * A dot's stagger start time, in ms from the draw's own start.
 *
 * Mostly linear across the draw window so the north-to-south order baked
 * into `AFRICA_DOTS` still reads as the map filling in from the top — but
 * with a small deterministic jitter, so 170 dots don't arrive as a scanline
 * sweeping down at a constant rate. Clamped into the window so the last dot
 * is always fully settled by `DRAW_DURATION_MS`, regardless of jitter.
 */
export function dotDelayMs(index: number, count: number): number {
  const span = Math.max(DRAW_DURATION_MS - DOT_SETTLE_MS, 0);
  if (span === 0 || count <= 1) return 0;
  const base = (index / (count - 1)) * span;
  const jitter = (seededUnit(index, 1) - 0.5) * span * 0.18;
  return clamp01((base + jitter) / span) * span;
}

/** A dot's scatter start offset from its true position, in the same
 *  normalised units as `AFRICA_DOTS`. Polar rather than independent x/y
 *  jitter so the scatter magnitude stays bounded in every direction instead
 *  of being larger on the diagonals. */
export function jitterOffset(index: number): readonly [number, number] {
  const angle = seededUnit(index, 2) * Math.PI * 2;
  const radius = SCATTER_MAGNITUDE * (0.5 + 0.5 * seededUnit(index, 3));
  return [Math.cos(angle) * radius, Math.sin(angle) * radius];
}

/** Eased pop-in progress for one dot: 0 before its delay, overshooting past
 *  1 partway through its settle window, exactly 1 once settled. */
export function settleProgress(elapsedMs: number, delayMs: number): number {
  const t = (elapsedMs - delayMs) / DOT_SETTLE_MS;
  return t <= 0 ? 0 : easeOutBack(t);
}

/** A dot's opacity: 0 until its delay, eased up to 1 over its settle
 *  window. Separate from `settleProgress` because alpha has no business
 *  overshooting past 1 the way the back-eased scale and position do. */
export function dotAlpha(elapsedMs: number, delayMs: number): number {
  return easeOutCubic((elapsedMs - delayMs) / DOT_SETTLE_MS);
}

/**
 * The ambient pulse's scale multiplier for a settled dot: 1 (no effect)
 * until the dot has finished settling and faded in, then a low-amplitude
 * wave whose phase depends on position, so it reads as travelling across
 * the mark rather than the whole mark breathing in lockstep.
 */
export function pulseFactor(
  elapsedMs: number,
  delayMs: number,
  x: number,
  y: number
): number {
  const settledAt = delayMs + DOT_SETTLE_MS;
  const sinceSettled = elapsedMs - settledAt;
  if (sinceSettled <= 0) return 1;
  const fadeIn = clamp01(sinceSettled / PULSE_FADE_IN_MS);
  const diagonal = x + y; // 0..~2: a cheap north-west to south-east ramp.
  const phase = elapsedMs / PULSE_PERIOD_MS - diagonal * PULSE_WAVE_DENSITY;
  const wave = Math.sin(phase * Math.PI * 2);
  return 1 + wave * PULSE_AMPLITUDE * fadeIn;
}

export type RGB = readonly [number, number, number];

// Matches `.heal-splash__line` / heal.teal.700 (tailwind.config.js) — the
// mark and the rule beneath it should read as the same brand teal, not two
// coincidentally similar ones.
const TEAL: RGB = [15, 118, 110];

// Sampled from the dominant fill of public/logo.png rather than picked off
// the Tailwind red ramp: that ramp (heal.red.*) is reserved elsewhere in the
// app for warnings and destructive actions, and this is the logo's own red,
// not a semantic one.
const RED: RGB = [198, 1, 9];

// heal.ink.900 — the same near-black already used for .heal-splash__name.
// Literal #000 read as a punched-out hole at the size these dots render at.
const BLACK: RGB = [31, 41, 51];

// No existing token for this. Picked to sit quietly against the splash's
// warm background and its pink/green halos rather than compete with them.
const YELLOW: RGB = [217, 149, 30];

interface PaletteStop {
  readonly color: RGB;
  readonly weight: number;
}

// Weight is dwell time in the loop, not a one-off pick. Red holds 85% of the
// cycle; the other three share the remaining 15% and are gone almost as soon
// as they arrive. The mark is red, crossed now and then by a fast band of
// something else — not four colours taking turns. Red leads the array as well
// as dominating it: the first stop is what a dot shows at the top of its
// cycle, so the mark resolves into the logo's own red and only ever flickers
// away from it.
//
// Teal was the dominant colour here. It is still the brand teal under the
// wordmark (`.heal-splash__line`), but a teal map above a teal rule read as
// one flat block of it — the mark carries the logo's red now and the rule
// carries the teal.
//
// These weights and HOLD_FRACTION move together. Shrinking a stop shortens
// its blend as well as its hold, so dropping one much further without raising
// the hold turns it from a flicker into a smudge.
export const PALETTE: readonly PaletteStop[] = [
  { color: RED, weight: 0.85 },
  { color: BLACK, weight: 0.06 },
  { color: TEAL, weight: 0.05 },
  { color: YELLOW, weight: 0.04 },
];

const TOTAL_WEIGHT = PALETTE.reduce((sum, stop) => sum + stop.weight, 0);

export function mix(a: RGB, b: RGB, t: number): RGB {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/**
 * Where in the colour cycle a dot sits, relative to the cycle's own clock.
 *
 * Position first, noise second — see `COLOR_SWEEP_SPAN`. Negated so the band
 * travels from the north-west down across the continent rather than up
 * against the direction the mark is drawn in.
 */
export function colorPhaseOffset(x: number, y: number, seed: number): number {
  return -(x + y) * COLOR_SWEEP_SPAN + (seed - 0.5) * COLOR_EDGE_DITHER;
}

/**
 * A dot's colour at a moment in time.
 *
 * Every dot rides the same weighted red -> black -> teal -> yellow -> red
 * loop, offset by `phaseOffset` — which `colorPhaseOffset` derives mostly
 * from where the dot sits, so the palette sweeps across the mark as a band
 * of colour rather than each dot changing on its own. Within each stop the
 * pure colour is held for `HOLD_FRACTION` of that stop's dwell before easing
 * into the next, so a dot is usually a clean palette colour and only briefly
 * in between.
 */
export function colorAt(phaseOffset: number, elapsedMs: number): RGB {
  const cyclePos = (((elapsedMs / COLOR_CYCLE_MS + phaseOffset) % 1) + 1) % 1;
  const target = cyclePos * TOTAL_WEIGHT;

  let acc = 0;
  for (let i = 0; i < PALETTE.length; i++) {
    const stop = PALETTE[i];
    if (target < acc + stop.weight || i === PALETTE.length - 1) {
      const next = PALETTE[(i + 1) % PALETTE.length];
      const localT = (target - acc) / stop.weight;
      if (localT < HOLD_FRACTION) return stop.color;
      const blendT = smoothstep((localT - HOLD_FRACTION) / (1 - HOLD_FRACTION));
      return mix(stop.color, next.color, blendT);
    }
    acc += stop.weight;
  }

  return PALETTE[0].color; // Unreachable given TOTAL_WEIGHT, but keeps this total.
}

export function toRgbString(color: RGB): string {
  return `rgb(${Math.round(color[0])}, ${Math.round(color[1])}, ${Math.round(color[2])})`;
}
