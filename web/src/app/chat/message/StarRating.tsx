"use client";

import { useState } from "react";
import { FiStar } from "react-icons/fi";

export const MAX_RATING = 4;

const LABELS: Record<number, string> = {
  1: "Not usable",
  2: "Partly useful",
  3: "Useful",
  4: "Exactly what I needed",
};

/**
 * Four stars, inline under the answer. 4 is best.
 *
 * Four rather than five because there is no neutral middle to hide in: a
 * health worker has to come down on one side of "was this usable". Rating is
 * one click and is submitted immediately — the comment is a separate, opt-in
 * step, so nobody is made to fill a form to say an answer was fine.
 */
export function StarRating({
  rating,
  onRate,
  disabled,
}: {
  rating?: number;
  onRate: (rating: number) => void;
  disabled?: boolean;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? rating ?? 0;

  return (
    <div className="flex items-center gap-1">
      <div
        className="flex items-center"
        onMouseLeave={() => setHovered(null)}
        role="radiogroup"
        aria-label="Rate this answer"
      >
        {Array.from({ length: MAX_RATING }, (_, i) => i + 1).map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={rating === value}
            aria-label={`${value} of ${MAX_RATING} — ${LABELS[value]}`}
            title={LABELS[value]}
            disabled={disabled}
            onMouseEnter={() => setHovered(value)}
            onClick={() => onRate(value)}
            className="rounded p-0.5 text-subtle transition-colors hover:text-accent disabled:cursor-default"
          >
            <FiStar
              size={15}
              className={
                value <= shown ? "fill-accent text-accent" : "text-border-strong"
              }
              aria-hidden="true"
            />
          </button>
        ))}
      </div>
      {shown > 0 && (
        <span className="text-[11px] text-subtle">{LABELS[shown]}</span>
      )}
    </div>
  );
}
