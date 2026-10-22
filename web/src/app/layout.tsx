import { Metadata } from "next";
import "./globals.css";
import { AppSplashScreen } from "@/components/AppSplashScreen";

import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

/**
 * IBM Plex Sans, chosen for what this app is read on and what it is read for.
 *
 * A health worker reads a dose off a cheap Android screen, at arm's length,
 * with a patient in front of them. Plex was drawn for technical material and
 * keeps its letterforms distinct at small sizes -- `1`, `l` and `I` do not
 * collapse into one another, and neither do `0` and `O`, which is the
 * difference between 10mg and lOmg on a bad screen.
 *
 * Self-hosted at build time by `next/font`, not fetched from Google at
 * runtime: a deployment on a slow Ugandan connection should not wait on a
 * third-party CDN to render its first sentence, and no reader's browser
 * should announce itself to one to read a clinical answer.
 *
 * Weights are explicit rather than variable. The variable file is the larger
 * download and nothing here needs a weight between the four named ones.
 */
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
  // Named so the fallback metrics match: a font that swaps in without this
  // reflows the whole answer as it arrives.
  fallback: [
    "system-ui",
    "-apple-system",
    "Segoe UI",
    "Roboto",
    "Helvetica Neue",
    "Arial",
    "sans-serif",
  ],
});

/**
 * For the places a value has to line up or be transcribed exactly: dose
 * strings in a code span, environment variable lines in the admin playground,
 * identifiers. Plex Mono is the same family's monospace, so those passages
 * read as part of the page rather than as a foreign paste.
 */
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  manifest: "/manifest.json",
  title: "HEAL",
  description: "Transforming Pandemic Preparedness in Uganda",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${plexSans.variable} ${plexMono.variable} font-sans text-default bg-background`}
      >
        <AppSplashScreen />
        {children}
      </body>
    </html>
  );
}
