/**
 * Types and pure logic for the retrieval playground.
 *
 * The screen's one obligation is to never misdescribe the run that produced
 * what is on it. Everything here that could get that wrong — which knobs were
 * moved, where the floor cut the list, how far under it a candidate fell — is a
 * pure function, kept out of the component so it can be tested.
 *
 * Defaults and bounds are NOT hardcoded here. They come from
 * `/manage/playground/options`, because the server is what enforces them: a
 * second copy would eventually disagree and the screen would start marking a
 * value as "default" when it was not.
 */

export interface ModelOption {
  id: string;
  display_name: string;
  provider: string;
  selectable: boolean;
  configured: boolean;
  /** Runs on our own infrastructure rather than a provider's. */
  self_hosted: boolean;
  notes: string;
}

/**
 * Every knob, keyed exactly as the API names them.
 *
 * Two stages, deliberately distinguished: the retrieval knobs decide what the
 * assistant is allowed to say, the generation ones only how it reads. A
 * temperature slider and a score floor do not carry the same clinical weight
 * and the screen should not imply they do.
 */
export interface TunableValues {
  min_retrieval_score: number;
  hybrid_alpha: number;
  hybrid_search: boolean;
  retrieval_top_k: number;
  context_top_k: number;
  max_chunks_per_source: number;
  temperature: number;
  max_output_tokens: number;
  top_p: number;
}

export interface PlaygroundOptions {
  models: ModelOption[];
  chat_model: string;
  classifier_model: string;
  defaults: TunableValues;
  bounds: Record<string, [number, number]>;
  knowledge_enabled: boolean;
}

export interface SettingUsed {
  name: string;
  /** "retrieval" or "generation". */
  stage: string;
  /** Environment variable that makes this value the default for every chat. */
  env_var: string;
  value: number | boolean;
  default: number | boolean;
  overridden: boolean;
  clamped: boolean;
  requested: number | boolean | null;
}

export interface Candidate {
  index: number;
  source_id: string;
  title: string;
  version: string;
  ordinal: number;
  text: string;
  truncated: boolean;
  dense_score: number;
  sparse_score: number;
  score: number;
  passed_floor: boolean;
  survived_cap: boolean;
  in_context: boolean;
  citation_number: number | null;
}

export interface Citation {
  marker: number;
  candidate_index: number;
  title: string;
  version: string;
}

export interface PlaygroundResult {
  question: string;
  understanding: {
    intent: string;
    original: string;
    query: string;
    terms: string[];
    lexical_query: string;
    classified: boolean;
    rewritten: boolean;
    model: string;
    error: string | null;
  };
  route: {
    intent: string;
    retrieve: boolean;
    require_source: boolean;
    answer: boolean;
  };
  candidates: Candidate[];
  citations: Citation[];
  settings: SettingUsed[];
  timings: {
    understand_ms: number;
    retrieve_ms: number;
    generate_ms: number;
    total_ms: number;
  };
  chat_model: string;
  classifier_model: string;
  answer: string | null;
  generated: boolean;
  retrieval_only: boolean;
  refused_unsourced: boolean;
  knowledge_enabled: boolean;
  unavailable: boolean;
  error: string | null;
}

export interface Tunable {
  name: keyof TunableValues;
  label: string;
  /** Why an admin would touch it. Shown under the control. */
  hint: string;
  step: number;
  /** Floats need a tolerance when compared; the k values do not. */
  float: boolean;
  stage: "retrieval" | "generation";
  /** Set this in the environment to make the value the default for all chats. */
  envVar: string;
}

export const NUMERIC_TUNABLES: Tunable[] = [
  {
    name: "min_retrieval_score",
    label: "Score floor",
    hint: "Below this the assistant cites nothing and refuses a dosage question.",
    step: 0.01,
    float: true,
    stage: "retrieval",
    envVar: "HEAL_MIN_RETRIEVAL_SCORE",
  },
  {
    name: "hybrid_alpha",
    label: "Dense weight",
    hint: "1.0 is meaning-only; 0.0 is exact-wording only. Drug codes need the lexical half.",
    step: 0.05,
    float: true,
    stage: "retrieval",
    envVar: "HEAL_HYBRID_ALPHA",
  },
  {
    name: "retrieval_top_k",
    label: "Candidates fetched",
    hint: "How many chunks come back from the store before any filtering.",
    step: 1,
    float: false,
    stage: "retrieval",
    envVar: "HEAL_RETRIEVAL_TOP_K",
  },
  {
    name: "context_top_k",
    label: "Passages in the prompt",
    hint: "How many survive to be numbered for the model to cite.",
    step: 1,
    float: false,
    stage: "retrieval",
    envVar: "HEAL_CONTEXT_TOP_K",
  },
  {
    name: "max_chunks_per_source",
    label: "Max per source",
    hint: "Stops one long guideline crowding out a corroborating second source.",
    step: 1,
    float: false,
    stage: "retrieval",
    envVar: "HEAL_MAX_CHUNKS_PER_SOURCE",
  },
  {
    name: "temperature",
    label: "Temperature",
    hint: "0 gives the same answer to the same question every time. Above 0 a model starts rewording, and this one quotes doses.",
    step: 0.05,
    float: true,
    stage: "generation",
    envVar: "HEAL_TEMPERATURE",
  },
  {
    name: "max_output_tokens",
    label: "Reply length",
    hint: "The verbosity cap. A health worker reading on a phone mid-consultation is not helped by six paragraphs.",
    step: 64,
    float: false,
    stage: "generation",
    envVar: "HEAL_MAX_OUTPUT_TOKENS",
  },
  {
    name: "top_p",
    label: "Top-p",
    hint: "Nucleus sampling. 1.0 disables it, and at temperature 0 it changes nothing either way.",
    step: 0.05,
    float: true,
    stage: "generation",
    envVar: "HEAL_TOP_P",
  },
];

/** Floats arrive from a slider and from JSON; an exact compare would lie. */
const EPSILON = 1e-9;

export function isOverridden(
  value: number | boolean,
  fallback: number | boolean
): boolean {
  if (typeof value === "boolean" || typeof fallback === "boolean") {
    return value !== fallback;
  }
  return Math.abs(value - fallback) > EPSILON;
}

/**
 * The knobs whose value differs from the deployment's own.
 *
 * Returned in the declared order so the "not the defaults" banner reads the
 * same way every time rather than in whichever order the admin happened to
 * touch things.
 */
export function changedNames(
  values: TunableValues,
  defaults: TunableValues
): (keyof TunableValues)[] {
  const order: (keyof TunableValues)[] = [
    "min_retrieval_score",
    "hybrid_alpha",
    "hybrid_search",
    "retrieval_top_k",
    "context_top_k",
    "max_chunks_per_source",
    "temperature",
    "max_output_tokens",
    "top_p",
  ];
  return order.filter((name) => isOverridden(values[name], defaults[name]));
}

/**
 * The request body: only what was actually moved.
 *
 * Sending every value would make the server report all six as "overridden",
 * and the screen would then shout about non-default settings on a run that
 * used nothing but the defaults.
 */
export function overridesFor(
  values: TunableValues,
  defaults: TunableValues
): Partial<TunableValues> {
  const body: Partial<TunableValues> = {};
  for (const name of changedNames(values, defaults)) {
    // The cast is safe: `name` indexes both objects with the same value type.
    (body as any)[name] = values[name];
  }
  return body;
}

/**
 * Where to draw the floor line: the number of candidates above it.
 *
 * Returns null when the line would sit at neither edge of nothing — an empty
 * list, everything above, or everything below. In those cases a line drawn
 * through the list says nothing the row badges do not already say, and a rule
 * floating above or below every row reads as a rendering bug.
 */
export function floorLineAfter(candidates: Candidate[]): number | null {
  if (candidates.length === 0) return null;
  const above = candidates.filter((c) => c.passed_floor).length;
  if (above === 0 || above === candidates.length) return null;
  return above;
}

/** How far under the floor a rejected candidate fell. Null if it passed. */
export function shortfall(candidate: Candidate, floor: number): number | null {
  if (candidate.passed_floor) return null;
  return Math.max(0, floor - candidate.score);
}

/** Four decimals, the precision the API rounds scores to. */
export function formatScore(score: number): string {
  return score.toFixed(4);
}

/** The floor as the run actually applied it, whatever the controls now read. */
export function appliedFloor(result: PlaygroundResult): number {
  const entry = result.settings.find((s) => s.name === "min_retrieval_score");
  return typeof entry?.value === "number" ? entry.value : 0;
}

/** Milliseconds as something readable at a glance. */
export function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function clampToBounds(
  value: number,
  bounds: [number, number] | undefined
): number {
  if (!bounds) return value;
  return Math.max(bounds[0], Math.min(bounds[1], value));
}
