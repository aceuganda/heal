import { useEffect, useState } from "react";
import { AfricaPulseLoader } from "@/components/health/AfricaPulseLoader";

/**
 * What a health worker sees between sending a question and the first token.
 *
 * That gap is the longest silence in the product -- a classification call, a
 * retrieval, then the model's own time to first token. A bare spinner says
 * only "something is happening"; this says what is happening, which is the
 * difference between waiting and wondering whether it broke.
 *
 * The wording is deliberately about the work, not about the machinery. A
 * health worker does not need to know how the system decides what to look up,
 * so nothing here names an internal step. They read as a colleague describing
 * what they are doing.
 */
const STEPS = [
  "Reading your question",
  "Searching approved guidelines",
  "Checking the reference library",
  "Matching clinical sources",
  "Preparing your answer",
];

// Typing is slower than deleting, the way a person writes and then wipes a
// line. The hold is what makes each step readable rather than a flicker.
const TYPE_MS = 45;
const DELETE_MS = 22;
const HOLD_MS = 1500;
const BETWEEN_MS = 250;

// Reduced motion still cycles the steps -- the information is the point, the
// letter-by-letter animation is not -- it just swaps them whole.
const REDUCED_HOLD_MS = 2600;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    // Read in an effect, not during render: `matchMedia` does not exist while
    // this is server-rendered.
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);

    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

function useTypedStep(reduced: boolean): string {
  const [step, setStep] = useState(0);
  const [typed, setTyped] = useState(0);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!reduced) {
      return;
    }
    const timer = setTimeout(
      () => setStep((current) => (current + 1) % STEPS.length),
      REDUCED_HOLD_MS
    );
    return () => clearTimeout(timer);
  }, [reduced, step]);

  useEffect(() => {
    if (reduced) {
      return;
    }
    const phrase = STEPS[step];

    // One timer per character, rescheduled from the state it just produced.
    // An interval would keep firing across a phrase change and type into the
    // wrong string.
    const advance = () => {
      if (!deleting && typed < phrase.length) {
        setTyped(typed + 1);
      } else if (!deleting) {
        setDeleting(true);
      } else if (typed > 0) {
        setTyped(typed - 1);
      } else {
        setDeleting(false);
        setStep((current) => (current + 1) % STEPS.length);
      }
    };

    let delay = DELETE_MS;
    if (!deleting) {
      delay = typed < phrase.length ? TYPE_MS : HOLD_MS;
    } else if (typed === 0) {
      delay = BETWEEN_MS;
    }

    const timer = setTimeout(advance, delay);
    return () => clearTimeout(timer);
  }, [reduced, step, typed, deleting]);

  return reduced ? STEPS[step] : STEPS[step].slice(0, typed);
}

export const AnswerProgress = ({ className }: { className?: string }) => {
  const reduced = usePrefersReducedMotion();
  const text = useTypedStep(reduced);

  return (
    <div className={`flex items-center gap-3 ${className || ""}`}>
      <AfricaPulseLoader size="2.5rem" label="Preparing your answer" />
      {/* aria-live is off: the loader beside it already announces a busy
          state, and reading five rotating steps aloud would be noise rather
          than information. */}
      <p className="text-sm text-subtle" aria-hidden="true">
        {text}
        <span className="ml-0.5 animate-pulse text-accent">|</span>
      </p>
    </div>
  );
};

export default AnswerProgress;
