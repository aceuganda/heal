"use client";

import { DotMark } from "@/components/splash/DotMark";

/**
 * The splash's dot mark, small, as the waiting state while the model works.
 *
 * Deliberately the same animation the app opens with rather than a second
 * idea: a health worker sees the mark assemble on launch, and seeing the same
 * continent draw itself again while an answer is being prepared reads as the
 * same product thinking, not as a new widget. It needs no loop to stay alive —
 * once assembled the mark keeps breathing and the colour band keeps travelling
 * across it, which is exactly the "still working" signal a spinner is for.
 *
 * Smaller than the splash on purpose. At 5.75rem the mark is the logo and the
 * thing you are looking at; beside a line of status text in a message list it
 * is punctuation, and anything near that size would shout over the answer it
 * is standing in for.
 *
 * `AfricaPulseLoader` is the loader this replaced here. It is still in the
 * tree and still works — it is kept for a use yet to be chosen, not orphaned
 * by accident.
 */

/** 2rem. Small enough to sit on a text line, large enough that 170 dots still
 *  resolve into a recognisable continent rather than a smudge. */
const DEFAULT_SIZE = "2rem";
const DEFAULT_SIZE_PX = 32;

interface DotMarkLoaderProps {
  /** CSS length for the mark's width; it is square. */
  size?: string;
  /** Extra classes for the wrapper. */
  className?: string;
  /** What assistive tech announces while this is on screen. */
  label?: string;
  /** `size` in pixels, for the single frame before layout is measured. Only
   *  worth passing alongside a non-default `size`. */
  fallbackSizePx?: number;
}

export function DotMarkLoader({
  size = DEFAULT_SIZE,
  className,
  label = "Preparing your answer",
  fallbackSizePx = DEFAULT_SIZE_PX,
}: DotMarkLoaderProps) {
  return (
    <div
      className={className ? `shrink-0 ${className}` : "shrink-0"}
      style={{ width: size, lineHeight: 0 }}
    >
      <DotMark role="status" label={label} fallbackSizePx={fallbackSizePx} />
    </div>
  );
}

export default DotMarkLoader;
