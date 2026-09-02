"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type SplashState = "shown" | "leaving" | "hidden";

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

    const leaveTimer = window.setTimeout(() => setState("leaving"), 1150);
    const removeTimer = window.setTimeout(() => setState("hidden"), 1500);

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
          <Image
            src="/logo.png"
            alt=""
            width={463}
            height={470}
            priority
          />
        </div>
        <span className="heal-splash__name">Heal</span>
        <span className="heal-splash__line" />
        <span className="heal-splash__tagline">Public health, closer to home</span>
      </div>
    </div>
  );
}
