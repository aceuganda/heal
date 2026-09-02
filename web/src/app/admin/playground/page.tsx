"use client";

/**
 * Retrieval playground — tune the pipeline, run a question, see what happened.
 *
 * `/admin/sources` already has a test search. This is the other half of the
 * same job: that panel shows what a query matches under the deployment's own
 * constants, and this one answers "what would a floor of 0.30 have let
 * through, for the question as retrieval actually saw it".
 *
 * Two properties the screen must never get wrong:
 *
 *   1. It says plainly, and permanently, that these settings apply to this run
 *      only. An admin who believes they have changed the live floor has been
 *      misled about a clinical-safety parameter.
 *   2. It reports the settings the SERVER says it used, never the ones the
 *      controls currently show. Those differ the moment a slider is moved
 *      after a run, and they differ when the server clamps a value into range.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  Badge,
  Button,
  Card,
  Text,
  TextInput,
  Title,
} from "@tremor/react";
import { LoadingButton } from "@/components/LoadingButton";
import { AdminPageTitle } from "@/components/admin/Title";
import { usePopup } from "@/components/admin/connectors/Popup";
import { ZoomInIcon } from "@/components/icons/icons";
import { fetcher } from "@/lib/fetcher";

import {
  appliedFloor,
  Candidate,
  changedNames,
  clampToBounds,
  floorLineAfter,
  formatMs,
  formatScore,
  isOverridden,
  isSaveable,
  NUMERIC_TUNABLES,
  overridesFor,
  PlaygroundOptions,
  PlaygroundResult,
  savePayload,
  shortfall,
  TunableValues,
} from "./lib";

const OPTIONS_URL = "/api/manage/playground/options";
const QUERY_URL = "/api/manage/playground/query";
const DEFAULTS_URL = "/api/manage/playground/defaults";

/**
 * FastAPI puts the message in `detail`, a string for a raised HTTPException
 * and a list of objects for a validation error. Rendering the latter straight
 * into a popup produces "[object Object]".
 */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) return `${first.msg} (${(first.loc ?? []).join(".")})`;
  }
  return `${fallback} (HTTP ${res.status})`;
}

function Switch({
  checked,
  onChange,
  label,
  hint,
  moved,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint: string;
  moved?: boolean;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? "bg-heal-teal-700" : "bg-heal-ink-300"
        }`}
      >
        <span
          className={`block h-4 w-4 rounded-full bg-white transition-transform ${
            checked ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </button>
      <span>
        <span className="text-sm font-medium text-heal-ink-900 flex gap-2">
          {label}
          {moved && <OverriddenTag />}
        </span>
        <span className="block text-xs text-heal-ink-500">{hint}</span>
      </span>
    </label>
  );
}

/** One consistent mark for "this is not what the deployment runs on". */
function OverriddenTag() {
  return (
    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
      changed
    </span>
  );
}

function NumberKnob({
  label,
  hint,
  value,
  fallback,
  step,
  envVar,
  bounds,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  fallback: number;
  step: number;
  envVar?: string;
  bounds: [number, number] | undefined;
  onChange: (next: number) => void;
}) {
  const moved = isOverridden(value, fallback);
  const [low, high] = bounds ?? [0, 100];

  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium text-heal-ink-900">{label}</span>
        {moved && <OverriddenTag />}
        <span className="ml-auto text-xs text-heal-ink-500">
          default {fallback}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-3">
        <input
          type="range"
          min={low}
          max={high}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="h-1 flex-1 accent-heal-teal-700"
        />
        <input
          type="number"
          min={low}
          max={high}
          step={step}
          value={value}
          // Clamped here as well as on the server. The server is the authority
          // — this only stops the slider rendering off its own track while the
          // number is being typed.
          onChange={(e) => onChange(clampToBounds(Number(e.target.value), bounds))}
          className="w-20 rounded border border-border px-2 py-1 text-sm"
        />
        {moved && (
          <button
            type="button"
            onClick={() => onChange(fallback)}
            className="text-xs text-link underline"
          >
            reset
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-heal-ink-500">{hint}</p>
      {moved && envVar && (
        <p className="mt-1 font-mono text-xs text-heal-ink-500">
          Keep it: {envVar}={value}
        </p>
      )}
    </div>
  );
}

/**
 * Answer length as a named level rather than a token number.
 *
 * The distinction is the whole point of the control: a token cap does not make
 * a model concise, it makes it stop — and the sentence it stops in the middle
 * of may be a dose. The level puts an instruction in the prompt, so the model
 * writes to length instead of being cut off at one.
 */
function VerbosityPicker({
  value,
  fallback,
  levels,
  cap,
  onChange,
}: {
  value: string;
  fallback: string;
  levels: PlaygroundOptions["verbosity_levels"];
  /** The configured hard ceiling, so the screen can say when it, not the
   * level, is what will end the answer. */
  cap: number;
  onChange: (next: string) => void;
}) {
  const moved = isOverridden(value, fallback);
  const chosen = levels.find((l) => l.name === value);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium text-heal-ink-900">Verbosity</span>
        {moved && <OverriddenTag />}
        <span className="ml-auto text-xs text-heal-ink-500">
          default {fallback}
        </span>
      </div>
      <div className="mt-1 flex gap-2">
        {levels.map((level) => (
          <button
            key={level.name}
            type="button"
            onClick={() => onChange(level.name)}
            className={`flex-1 rounded border px-2 py-1.5 text-sm ${
              level.name === value
                ? "border-heal-teal-700 bg-heal-teal-700/10 font-semibold text-heal-teal-900"
                : "border-border text-heal-ink-700"
            }`}
          >
            {level.label}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-heal-ink-500">
        {chosen?.hint ?? "How long an answer should be."}
      </p>
      {chosen && chosen.budget > cap && (
        // Otherwise an admin picks "detailed", gets a short answer, and has no
        // way to see that the ceiling — not the level — is what ended it.
        <p className="mt-1 text-xs text-amber-700">
          The hard ceiling of {cap} tokens is lower than this level&rsquo;s{" "}
          {chosen.budget}, so the ceiling is what will stop the answer.
        </p>
      )}
    </div>
  );
}

function ModelPicker({
  label,
  value,
  fallback,
  options,
  onChange,
}: {
  label: string;
  value: string;
  fallback: string;
  options: PlaygroundOptions["models"];
  onChange: (next: string) => void;
}) {
  const moved = value !== "" && value !== fallback;
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium text-heal-ink-900">{label}</span>
        {moved && <OverriddenTag />}
        <span className="ml-auto text-xs text-heal-ink-500">
          default {fallback}
        </span>
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
      >
        <option value="">Deployment default ({fallback})</option>
        {options.map((model) => (
          <option key={model.id} value={model.id}>
            {model.display_name}
            {model.self_hosted ? " — internal" : ""}
            {model.configured ? "" : " — no API key set"}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * The standing warning. Deliberately not dismissible and not conditional on
 * anything having been changed: the sentence an admin needs is that nothing
 * here reaches a health worker, and that is true before they touch a control.
 */
function ScopeNotice() {
  return (
    <Card className="mb-6 border-l-4 border-l-heal-teal-700">
      <Title>Runs are private; saving is not</Title>
      <Text className="mt-2">
        Every value below travels with the one request you send and is discarded
        when it finishes. Concurrent conversations keep using the
        deployment&rsquo;s own configuration, and the live score floor is
        unchanged by anything you try here.
      </Text>
      <Text className="mt-2">
        The exception is <b>Save as deployment default</b>, which is the one
        action on this page that outlives its request: it changes how every
        subsequent answer is worded, immediately, for everybody. Only the
        wording settings and the model choice can be saved. The retrieval
        settings stay per-run — the score floor decides whether a dose may be
        quoted at all, so it is changed in the deployment&rsquo;s environment
        against measured results, not from a slider.
      </Text>
    </Card>
  );
}

/** What the deployment is running on right now, and where each value came from. */
function DeploymentDefaults({
  options,
  onRevert,
  busy,
}: {
  options: PlaygroundOptions;
  onRevert: () => void;
  busy: boolean;
}) {
  const rows: { name: string; label: string; value: string }[] = [
    { name: "chat_model", label: "Chat model", value: options.chat_model },
    {
      name: "classifier_model",
      label: "Classifier",
      value: options.classifier_model,
    },
    {
      name: "verbosity",
      label: "Verbosity",
      value: String(options.defaults.verbosity),
    },
    {
      name: "temperature",
      label: "Temperature",
      value: String(options.defaults.temperature),
    },
    { name: "top_p", label: "Top-p", value: String(options.defaults.top_p) },
    {
      name: "max_output_tokens",
      label: "Token ceiling",
      value: String(options.defaults.max_output_tokens),
    },
  ];
  const saved = rows.filter((r) => options.sources[r.name] === "saved");

  return (
    <Card className="mb-6">
      <div className="flex items-baseline gap-3">
        <Title>What every chat runs on now</Title>
        {saved.length > 0 && (
          <span className="rounded bg-heal-teal-700/10 px-2 py-0.5 text-xs font-semibold text-heal-teal-900">
            {saved.length} saved here
          </span>
        )}
      </div>
      <Text className="mt-1">
        {saved.length === 0
          ? "Every value is the deployment’s environment. Nothing has been overridden from this screen."
          : `Saved values override the environment until they are cleared${
              options.updated_by ? `. Last changed by ${options.updated_by}` : ""
            }${
              options.updated_at
                ? ` on ${new Date(options.updated_at).toLocaleString()}`
                : ""
            }.`}
      </Text>
      <div className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
        {rows.map((row) => {
          const isSaved = options.sources[row.name] === "saved";
          return (
            <div key={row.name}>
              <div className="text-xs uppercase tracking-wide text-heal-ink-500">
                {row.label}
              </div>
              <div className="text-sm font-semibold text-heal-ink-900">
                {row.value}{" "}
                {isSaved ? (
                  <span className="text-xs font-normal text-heal-teal-800">
                    saved
                  </span>
                ) : (
                  <span className="text-xs font-normal text-heal-ink-500">
                    from the environment
                  </span>
                )}
              </div>
              {isSaved && (
                // The environment is still the default underneath. Showing what
                // it says is what makes "clear this" a decision rather than a
                // leap.
                <div className="text-xs text-heal-ink-500">
                  environment says {String(options.env_defaults[row.name])}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {saved.length > 0 && (
        <button
          type="button"
          disabled={busy}
          onClick={onRevert}
          className="mt-4 text-xs text-link underline disabled:opacity-50"
        >
          Clear all saved values and follow the environment again
        </button>
      )}
    </Card>
  );
}

function SettingsUsed({ result }: { result: PlaygroundResult }) {
  const changed = result.settings.filter((s) => s.overridden);

  return (
    <Card
      className={`mb-4 ${changed.length ? "border-l-4 border-l-amber-500" : ""}`}
    >
      <div className="flex items-baseline gap-3">
        <Title>Settings this run used</Title>
        {changed.length > 0 && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
            {changed.length} non-default
          </span>
        )}
      </div>
      {changed.length === 0 && (
        <Text className="mt-1">
          Every value was the deployment&rsquo;s own, so this result is what a
          health worker asking the same question would have got.
        </Text>
      )}
      <div className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
        {result.settings.map((setting) => (
          <div key={setting.name}>
            <div className="text-xs uppercase tracking-wide text-heal-ink-500">
              {setting.name.replace(/_/g, " ")}
            </div>
            <div className="text-sm font-semibold text-heal-ink-900">
              {String(setting.value)}{" "}
              {setting.overridden ? (
                <span className="text-xs font-normal text-amber-700">
                  overridden (default {String(setting.default)})
                </span>
              ) : (
                <span className="text-xs font-normal text-heal-ink-500">
                  default
                </span>
              )}
            </div>
            {setting.clamped && (
              // The one case where the screen would otherwise show a number
              // nobody asked for.
              <div className="text-xs text-error">
                you asked for {String(setting.requested)} — clamped into range
              </div>
            )}
          </div>
        ))}
        <div>
          <div className="text-xs uppercase tracking-wide text-heal-ink-500">
            models
          </div>
          <div className="text-sm font-semibold text-heal-ink-900">
            {result.chat_model}{" "}
            <span className="text-xs font-normal text-heal-ink-500">
              chat / {result.classifier_model} classifier
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}

function UnderstandingPanel({ result }: { result: PlaygroundResult }) {
  const u = result.understanding;
  return (
    <Card className="mb-4">
      <Title>What retrieval searched on</Title>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-heal-ink-500">
            As typed
          </div>
          <p className="mt-1 text-sm text-heal-ink-700">{u.original}</p>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-heal-ink-500">
            Rewritten for search
          </div>
          <p className="mt-1 text-sm font-medium text-heal-ink-900">{u.query}</p>
          {!u.rewritten && (
            <p className="mt-1 text-xs text-error">
              The rewrite was not used{u.error ? ` (${u.error})` : ""} — the
              search ran on the original wording, which is the safe fallback.
            </p>
          )}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge color={u.classified ? "emerald" : "amber"}>{u.intent}</Badge>
        <span className="text-xs text-heal-ink-500">
          {result.route.retrieve ? "retrieves" : "does not retrieve"} ·{" "}
          {result.route.require_source
            ? "refuses without an approved source"
            : "may answer unsourced"}
        </span>
        {u.terms.length > 0 && (
          <span className="text-xs text-heal-ink-500">
            terms kept verbatim: {u.terms.join(", ")}
          </span>
        )}
      </div>
    </Card>
  );
}

function CandidateRow({
  candidate,
  floor,
}: {
  candidate: Candidate;
  floor: number;
}) {
  const missedBy = shortfall(candidate, floor);
  return (
    <div
      className={`border-l-2 py-2 pl-3 ${
        candidate.in_context
          ? "border-l-heal-teal-600"
          : candidate.passed_floor
          ? "border-l-heal-ink-300"
          : "border-l-transparent opacity-70"
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
        <span className="font-mono text-heal-ink-400">#{candidate.index}</span>
        <span className="font-semibold text-heal-ink-900">
          {formatScore(candidate.score)}
        </span>
        <span className="text-heal-ink-500">
          dense {formatScore(candidate.dense_score)} · lexical{" "}
          {formatScore(candidate.sparse_score)}
        </span>
        <span className="text-heal-ink-500">
          {candidate.title} v{candidate.version} · chunk {candidate.ordinal}
        </span>
        {candidate.citation_number !== null && (
          <Badge color="teal">cited as [{candidate.citation_number}]</Badge>
        )}
        {missedBy !== null && (
          <span className="text-error">
            below the floor by {formatScore(missedBy)}
          </span>
        )}
        {candidate.passed_floor && !candidate.survived_cap && (
          <span className="text-amber-700">
            cut by the per-source cap, not by the floor
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-heal-ink-700">
        {candidate.text}
        {candidate.truncated && <span className="text-heal-ink-400">…</span>}
      </p>
    </div>
  );
}

/** The line itself. The whole panel exists so this is visible. */
function FloorLine({ floor }: { floor: number }) {
  return (
    <div className="my-3 flex items-center gap-3">
      <div className="h-px flex-1 bg-error" />
      <span className="whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-error">
        score floor {formatScore(floor)} — everything below is discarded
      </span>
      <div className="h-px flex-1 bg-error" />
    </div>
  );
}

function CandidatesPanel({ result }: { result: PlaygroundResult }) {
  const floor = appliedFloor(result);
  const lineAfter = floorLineAfter(result.candidates);
  const allBelow =
    result.candidates.length > 0 && result.candidates.every((c) => !c.passed_floor);

  return (
    <Card className="mb-4">
      <Title>Candidates, before the floor and the cap</Title>
      <Text className="mt-1 mb-3">
        Every chunk the store returned, in fused rank order. The ones below the
        line are what this floor throws away.
      </Text>

      {result.unavailable && (
        <Text className="text-error">
          The vector store could not be reached ({result.error}). No ranking to
          show.
        </Text>
      )}
      {!result.unavailable && result.candidates.length === 0 && (
        <Text>
          Nothing matched at all. Only approved, current sources are searched —
          check <code>/admin/sources</code>.
        </Text>
      )}
      {allBelow && (
        <Text className="mb-3 text-error">
          Every candidate is below the floor of {formatScore(floor)}, so the
          assistant would cite nothing here.
        </Text>
      )}

      {result.candidates.map((candidate, i) => (
        <div key={candidate.index}>
          {lineAfter === i && <FloorLine floor={floor} />}
          <CandidateRow candidate={candidate} floor={floor} />
        </div>
      ))}
    </Card>
  );
}

function AnswerPanel({ result }: { result: PlaygroundResult }) {
  if (result.refused_unsourced) {
    return (
      <Card className="mb-4 border-l-4 border-l-error">
        <Title>Refused for lack of an approved source</Title>
        <Text className="mt-2">
          The route for this intent requires a source, and nothing survived the
          floor. A health worker would be told to check the guideline rather
          than given a dose from memory. Lower the floor above to see what was
          nearly good enough.
        </Text>
      </Card>
    );
  }

  if (result.retrieval_only) {
    return (
      <Card className="mb-4">
        <Title>Generation skipped</Title>
        <Text className="mt-2">
          Retrieval only. Switch it off to see the answer these passages
          produce.
        </Text>
      </Card>
    );
  }

  if (result.error && !result.unavailable) {
    return (
      <Card className="mb-4 border-l-4 border-l-error">
        <Title>Generation failed</Title>
        <Text className="mt-2">{result.error}</Text>
      </Card>
    );
  }

  if (!result.generated) return null;

  return (
    <Card className="mb-4">
      <Title>Answer</Title>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-heal-ink-800">
        {result.answer}
      </pre>
      {result.citations.length > 0 ? (
        <div className="mt-4 border-t border-border pt-3">
          <div className="text-xs uppercase tracking-wide text-heal-ink-500">
            Markers the answer used
          </div>
          <ul className="mt-1 text-sm">
            {result.citations.map((citation) => (
              <li key={citation.marker} className="text-heal-ink-700">
                <span className="font-semibold">[{citation.marker}]</span> →
                candidate #{citation.candidate_index} · {citation.title} v
                {citation.version}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Text className="mt-3 text-xs">
          The answer cited nothing. With passages in the prompt that is worth
          looking at: it means the model did not lean on them.
        </Text>
      )}
    </Card>
  );
}

function TimingsPanel({ result }: { result: PlaygroundResult }) {
  const stages: [string, number][] = [
    ["Understand", result.timings.understand_ms],
    ["Retrieve", result.timings.retrieve_ms],
    ["Generate", result.timings.generate_ms],
    ["Total", result.timings.total_ms],
  ];
  return (
    <Card className="mb-4">
      <div className="flex flex-wrap gap-x-10 gap-y-3">
        {stages.map(([label, ms]) => (
          <div key={label}>
            <div className="text-xs uppercase tracking-wide text-heal-ink-500">
              {label}
            </div>
            <div className="text-sm font-semibold text-heal-ink-900">
              {formatMs(ms)}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function Page() {
  const { popup, setPopup } = usePopup();
  const { data: options, mutate: reloadOptions } = useSWR<PlaygroundOptions>(
    OPTIONS_URL,
    fetcher
  );

  const [question, setQuestion] = useState("");
  const [values, setValues] = useState<TunableValues | null>(null);
  const [chatModel, setChatModel] = useState("");
  const [classifierModel, setClassifierModel] = useState("");
  const [retrievalOnly, setRetrievalOnly] = useState(false);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);

  // The controls start on the server's defaults rather than on a copy compiled
  // into the bundle, so "default" on this screen always means the value this
  // deployment is actually running.
  const current = values ?? options?.defaults ?? null;
  const changed = useMemo(
    () =>
      current && options ? changedNames(current, options.defaults) : [],
    [current, options]
  );

  const set = (patch: Partial<TunableValues>) => {
    if (!current) return;
    setValues({ ...current, ...patch });
  };

  const run = async () => {
    if (!question.trim() || !options || !current) return;
    setBusy(true);
    try {
      const res = await fetch(QUERY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          retrieval_only: retrievalOnly,
          ...(chatModel ? { chat_model: chatModel } : {}),
          ...(classifierModel ? { classifier_model: classifierModel } : {}),
          ...overridesFor(current, options.defaults),
        }),
      });
      if (!res.ok) {
        setPopup({ message: await errorMessage(res, "Run failed"), type: "error" });
        return;
      }
      setResult(await res.json());
    } catch (e) {
      setPopup({ message: `Run failed: ${e}`, type: "error" });
    } finally {
      setBusy(false);
    }
  };

  /**
   * Write settings the whole deployment will run on.
   *
   * The one action here that leaves the page. `body` carries only the keys
   * being changed: an absent key means "leave it alone" and a null one means
   * "clear it back to the environment", and conflating the two would quietly
   * pin knobs the admin never touched.
   */
  const persist = async (
    body: Record<string, number | string | null>,
    message: string
  ) => {
    setSaving(true);
    try {
      const res = await fetch(DEFAULTS_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setPopup({ message: await errorMessage(res, "Save failed"), type: "error" });
        return;
      }
      // Re-read rather than patching local state: the server clamps, and the
      // screen must show the value it stored, not the one that was sent.
      await reloadOptions();
      // The controls now sit on the new deployment defaults, so nothing is
      // marked "changed" straight after saving it.
      setValues(null);
      setChatModel("");
      setClassifierModel("");
      setPopup({ message, type: "success" });
    } catch (e) {
      setPopup({ message: `Save failed: ${e}`, type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const saveDefaults = () => {
    if (!options || !current) return;
    const body = savePayload(current, options.defaults, chatModel, classifierModel);
    const names = Object.keys(body);
    if (names.length === 0) return;
    if (
      !window.confirm(
        `Save ${names.join(", ")} as the deployment default?\n\n` +
          "This changes how every answer is worded, for every user, from the " +
          "next message onwards."
      )
    ) {
      return;
    }
    void persist(body, `Saved ${names.length} setting(s) for every chat.`);
  };

  const revertDefaults = () => {
    if (!options) return;
    const saved = Object.entries(options.sources)
      .filter(([, source]) => source === "saved")
      .map(([name]) => name);
    if (saved.length === 0) return;
    if (
      !window.confirm(
        `Clear ${saved.join(", ")} and follow the environment again?`
      )
    ) {
      return;
    }
    // Explicit nulls: this is a reset, not an omission.
    void persist(
      Object.fromEntries(saved.map((name) => [name, null])),
      "Cleared. Every value follows the environment again."
    );
  };

  return (
    <div className="container mx-auto">
      {popup}
      <AdminPageTitle
        icon={<ZoomInIcon size={32} />}
        title="Retrieval playground"
      />
      <ScopeNotice />

      {options && (
        <DeploymentDefaults
          options={options}
          onRevert={revertDefaults}
          busy={saving}
        />
      )}

      {options && !options.knowledge_enabled && (
        <Card className="mb-6 border-error">
          <Title className="text-error">Retrieval is switched off</Title>
          <Text className="mt-2">
            This deployment runs with <code>KNOWLEDGE_ENABLED=false</code>, so
            there is nothing to retrieve from. The understand step and the route
            table still run.
          </Text>
        </Card>
      )}

      <Card className="mb-6">
        <Title>Ask</Title>
        <div className="mt-3 flex max-w-3xl gap-2">
          <TextInput
            placeholder='e.g. "wat z the dose of TDF/3TC/DTG for a 14yr old, she weighs 40kg"'
            value={question}
            onValueChange={setQuestion}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
          <LoadingButton onClick={run} disabled={busy || !current} loading={busy}>
            {busy ? "Running…" : "Run"}
          </LoadingButton>
        </div>

        {current && options && (
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="flex flex-col gap-5">
              <Switch
                label="Hybrid search"
                hint="Dense meaning search fused with lexical matching. Off is dense only, which is where drug codes get lost."
                checked={current.hybrid_search}
                moved={isOverridden(
                  current.hybrid_search,
                  options.defaults.hybrid_search
                )}
                onChange={(next) => set({ hybrid_search: next })}
              />
              <Switch
                label="Retrieval only"
                hint="Skip generation. Faster, and free, while tuning the floor."
                checked={retrievalOnly}
                onChange={setRetrievalOnly}
              />
              <ModelPicker
                label="Chat model"
                value={chatModel}
                fallback={options.chat_model}
                options={options.models}
                onChange={setChatModel}
              />
              <ModelPicker
                label="Classifier model"
                value={classifierModel}
                fallback={options.classifier_model}
                options={options.models}
                onChange={setClassifierModel}
              />
            </div>

            <div className="flex flex-col gap-5">
              {(["retrieval", "generation"] as const).map((stage) => (
                <div key={stage} className="flex flex-col gap-5">
                  <div className="border-b border-border pb-1">
                    <div className="text-xs font-semibold uppercase tracking-wide text-heal-ink-900">
                      {stage === "retrieval" ? "Retrieval" : "Wording"}
                    </div>
                    <p className="mt-0.5 text-xs text-heal-ink-500">
                      {stage === "retrieval"
                        ? "Decides what the assistant is allowed to say."
                        : "Decides only how the answer reads, not what it may claim."}
                    </p>
                  </div>
                  {stage === "generation" && (
                    <VerbosityPicker
                      value={String(current.verbosity)}
                      fallback={String(options.defaults.verbosity)}
                      levels={options.verbosity_levels}
                      cap={current.max_output_tokens}
                      onChange={(next) => set({ verbosity: next })}
                    />
                  )}
                  {NUMERIC_TUNABLES.filter((t) => t.stage === stage).map(
                    (tunable) => (
                      <NumberKnob
                        key={tunable.name}
                        label={tunable.label}
                        hint={tunable.hint}
                        step={tunable.step}
                        envVar={tunable.envVar}
                        bounds={options.bounds[tunable.name]}
                        value={current[tunable.name] as number}
                        fallback={options.defaults[tunable.name] as number}
                        onChange={(next) =>
                          set({ [tunable.name]: next } as Partial<TunableValues>)
                        }
                      />
                    )
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {(changed.length > 0 || chatModel || classifierModel) && (
          <div className="mt-5 rounded border-l-4 border-l-amber-500 bg-amber-50 px-4 py-3">
            <div className="text-sm font-semibold text-amber-900">
              {changed.length > 0
                ? `This run will use ${changed.length} non-default setting${
                    changed.length === 1 ? "" : "s"
                  }`
                : "This run will use a different model"}
            </div>
            <div className="mt-1 text-xs text-amber-800">
              {[
                ...changed.map((name) => name.replace(/_/g, " ")),
                ...(chatModel ? [`chat model ${chatModel}`] : []),
                ...(classifierModel
                  ? [`classifier model ${classifierModel}`]
                  : []),
              ].join(", ")}{" "}
              — for this request only. Health workers are unaffected.
            </div>
            {/* The tuning is worthless if you cannot keep the value you liked.
                The wording knobs can be saved from here; the retrieval ones
                are shown as the environment lines that would set them, which
                is deliberate — see ScopeNotice. */}
            {(changed.some((name) => isSaveable(name)) ||
              chatModel ||
              classifierModel) && (
              <div className="mt-3 rounded bg-white/70 px-3 py-2">
                <div className="text-xs font-semibold text-amber-900">
                  Keep{" "}
                  {changed
                    .filter((name) => isSaveable(name))
                    .map((name) => name.replace(/_/g, " "))
                    .join(", ")}
                  {chatModel || classifierModel ? " and the model choice" : ""}?
                </div>
                <LoadingButton
                  size="xs"
                  className="mt-2"
                  loading={saving}
                  disabled={saving}
                  onClick={saveDefaults}
                >
                  Save as deployment default
                </LoadingButton>
                <div className="mt-1 text-xs text-amber-800">
                  Applies to every chat from the next message. No restart.
                </div>
              </div>
            )}
            {changed.some((name) => !isSaveable(name)) && (
              <div className="mt-2 rounded bg-amber-100/70 px-3 py-2">
                <div className="text-xs font-semibold text-amber-900">
                  The retrieval settings are not saveable from here. To make
                  them the default, set:
                </div>
                <pre className="mt-1 overflow-x-auto font-mono text-xs text-amber-900">
                  {changed
                    .filter((name) => !isSaveable(name))
                    .map((name) => {
                      const tunable = NUMERIC_TUNABLES.find(
                        (t) => t.name === name
                      );
                      const envVar =
                        tunable?.envVar ?? `HEAL_${name.toUpperCase()}`;
                      return `${envVar}=${current ? current[name] : ""}`;
                    })
                    .join("\n")}
                </pre>
                <div className="mt-1 text-xs text-amber-800">
                  Then restart the API. The score floor decides whether a dose
                  may be quoted at all, so it is changed against measured
                  results rather than from this screen.
                </div>
              </div>
            )}
            <button
              type="button"
              className="mt-2 text-xs text-amber-900 underline"
              onClick={() => setValues(options ? { ...options.defaults } : null)}
            >
              Reset everything to the deployment defaults
            </button>
          </div>
        )}
      </Card>

      {result && (
        <>
          <SettingsUsed result={result} />
          <UnderstandingPanel result={result} />
          <TimingsPanel result={result} />
          <CandidatesPanel result={result} />
          <AnswerPanel result={result} />
        </>
      )}
    </div>
  );
}
