"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { DotMark } from "@/components/splash/DotMark";

type SplashState = "shown" | "leaving" | "hidden";

/**
 * How long the splash holds before it starts fading.
 *
 * The dot-draw finishes at `DRAW_DURATION_MS` (780ms), so anything close to
 * that cuts the fade in over a mark that has only just landed. This leaves
 * the assembled mark up for well over a second of its own — the colour band
 * gets to travel across the continent at least once, which is the part that
 * was previously being thrown away.
 */
const SPLASH_HOLD_MS = 2150;

/** The fade itself — matches `.heal-splash`'s 350ms opacity transition, plus
 *  a frame's slack so the element is not removed mid-fade. */
const SPLASH_FADE_MS = 350;

/**
 * A short brand moment for the app shell. Authentication screens deliberately
 * stay direct so sign-in and verification are never delayed by the splash.
 */
export function AppSplashScreen() {
  const pathname = usePathname();
  const [state, setState] = useState<SplashState>("shown");
  const isAuthPage = pathname?.startsWith("/auth");

  useEffect(() => {
    if (isAuthPage) {
      return;
    }

    const leaveTimer = window.setTimeout(() => setState("leaving"), SPLASH_HOLD_MS);
    const removeTimer = window.setTimeout(
      () => setState("hidden"),
      SPLASH_HOLD_MS + SPLASH_FADE_MS
    );

    return () => {
      window.clearTimeout(leaveTimer);
      window.clearTimeout(removeTimer);
    };
  }, [isAuthPage]);

  if (isAuthPage || state === "hidden") {
    return null;
  }

  return (
    <div
      className={`heal-splash ${state === "leaving" ? "heal-splash--leaving" : ""}`}
      role="status"
      aria-label="Loading Heal"
    >
      <div className="heal-splash__halo heal-splash__halo--one" />
      <div className="heal-splash__halo heal-splash__halo--two" />

      <div className="heal-splash__brand">
        <div className="heal-splash__mark">
          <DotMark />
        </div>
        <span className="heal-splash__name">Heal</span>
        <span className="heal-splash__line" />
        {/* The name written out. "Heal" alone reads as a verb; what the
            product is only becomes clear when it is spelled out. */}
        <span className="heal-splash__tagline">AI for Health Equity</span>
      </div>
    </div>
  );
}
