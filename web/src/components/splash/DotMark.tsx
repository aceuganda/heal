"use client";

import { useEffect, useRef } from "react";

import { AFRICA_DOTS, DOT_RADIUS } from "./africaDots";
import {
  colorAt,
  colorPhaseOffset,
  dotAlpha,
  dotDelayMs,
  jitterOffset,
  pulseFactor,
  seededUnit,
  settleProgress,
  toRgbString,
} from "./dotAnimation";

/** Scale a settling dot starts at, before its back-ease overshoot carries it
 *  past 1. Nonzero (rather than starting from nothing) because alpha is
 *  already doing the "materialising" work; a dot popping in from true zero
 *  scale reads as appearing rather than arriving. */
const MIN_SCALE = 0.3;

/** Matches `.heal-splash__mark`'s `width: 5.75rem` at the default root font
 *  size. Only used if the canvas is measured before CSS has applied a real
 *  size to it — the ResizeObserver below corrects this the moment layout
 *  settles, so this is a one-frame fallback, not the real sizing path. */
const DEFAULT_FALLBACK_SIZE_PX = 92;

interface DotMarkProps {
  /** Applied on top of `.heal-dot-mark`. The mark takes its size from
   *  whatever box it is given, so this is how a caller shrinks it. */
  className?: string;
  /** Accessible name. "Heal" on the splash, where the mark is the logo;
   *  something about the wait wherever it is standing in for a spinner. */
  label?: string;
  /** `status` where the mark means "working", so assistive tech announces it
   *  as a live busy state rather than as a picture. */
  role?: "img" | "status";
  /** One-frame fallback before layout settles. Worth setting when the mark
   *  is rendered much smaller than the splash's 5.75rem, so the first frame
   *  is not drawn at four times its final size. */
  fallbackSizePx?: number;
}

/**
 * The Heal mark, redrawn dot by dot rather than shown as the static PNG.
 *
 * Used at 5.75rem on the splash and small in chat, where it stands in for a
 * spinner while the model works. Nothing here is splash-specific: the mark
 * assembles once and then keeps breathing and cycling colour indefinitely,
 * which is a loading state as much as it is an entrance.
 *
 * Canvas over 170 animated SVG circles: each of those would be a DOM node
 * getting a transform and a fill rewritten every frame, and on the low-end
 * Android hardware this app has to run on that is a real jank risk during
 * the one moment the app is making a first impression. A canvas redraw of
 * 170 circles is one draw call's worth of work per frame regardless of
 * device, and nothing here needs to be a DOM node — there is no per-dot
 * interactivity or accessibility content to hang off one.
 */
export function DotMark({
  className,
  label = "Heal",
  role = "img",
  fallbackSizePx = DEFAULT_FALLBACK_SIZE_PX,
}: DotMarkProps = {}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    const start = performance.now();
    let size = fallbackSizePx;
    let frame = 0;
    let cancelled = false;

    // The canvas is square (see africaDots.ts: x and y are each normalised
    // over the mark's own bounding box, which is near-enough square that the
    // ~1% difference between the source PNG's 463x470 is not worth a second
    // aspect ratio to track). Sized by CSS width, with the backing store
    // scaled by devicePixelRatio so the dots stay crisp on retina.
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      size = rect.width || fallbackSizePx;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (elapsedMs: number) => {
      ctx.clearRect(0, 0, size, size);

      for (let i = 0; i < AFRICA_DOTS.length; i++) {
        const [tx, ty] = AFRICA_DOTS[i];
        const seed = seededUnit(i);

        let x = tx;
        let y = ty;
        let scale = 1;
        let alpha = 1;
        let colorTime = 0;

        if (!reduceMotion) {
          const delay = dotDelayMs(i, AFRICA_DOTS.length);
          const settle = settleProgress(elapsedMs, delay);
          const [jx, jy] = jitterOffset(i);
          const drift = 1 - settle;
          x = tx + jx * drift;
          y = ty + jy * drift;
          scale =
            (MIN_SCALE + (1 - MIN_SCALE) * settle) *
            pulseFactor(elapsedMs, delay, tx, ty);
          alpha = dotAlpha(elapsedMs, delay);
          colorTime = elapsedMs;
        }

        const radius = Math.max(DOT_RADIUS * size * scale, 0);
        ctx.globalAlpha = alpha;
        // Phase from the dot's position, so the palette crosses the mark as a
        // band. Held still at colorTime 0 under reduced motion, which leaves
        // that same band laid across a mark that simply does not move.
        ctx.fillStyle = toRgbString(
          colorAt(colorPhaseOffset(tx, ty, seed), colorTime)
        );
        ctx.beginPath();
        ctx.arc(x * size, y * size, radius, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.globalAlpha = 1;
    };

    resize();
    draw(0);

    // getBoundingClientRect() above can still report 0 on first paint (the
    // splash mounts before layout has necessarily settled), and separately
    // the container's real size might not be known yet at all. Either way,
    // this repaints once layout catches up instead of leaving the mark
    // stuck at the fallback size or blank.
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => {
        resize();
        draw(reduceMotion ? 0 : performance.now() - start);
      });
      observer.observe(canvas);
    }

    if (!reduceMotion) {
      const tick = (now: number) => {
        if (cancelled) return;
        draw(now - start);
        frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }

    return () => {
      cancelled = true;
      if (frame) cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [fallbackSizePx]);

  return (
    <canvas
      ref={canvasRef}
      className={className ? `heal-dot-mark ${className}` : "heal-dot-mark"}
      role={role}
      aria-label={label}
    />
  );
}
