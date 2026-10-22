/**
 * Regression guard for the React 19 crash in Tremor's busy button.
 *
 * Tremor's `Button` runs its `loading` state through a react-transition-group
 * `Transition` with no `nodeRef`, so the first flip calls the `findDOMNode`
 * that React 19 removed. Every admin action button threw on the click that
 * started the work. `LoadingButton` draws the spinner itself and never passes
 * `loading` down; this test fails if a `loading` prop finds its way back onto a
 * Tremor `Button`.
 *
 * A file scan rather than a render: the web app has no jsdom or component
 * testing set up, and the mistake is visible in the source anyway.
 */
import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

/** Every live .tsx under src/. `deprecated/` is dead text nothing routes to. */
function liveComponentFiles(dir: string = SRC): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry === "deprecated" || entry === "node_modules") continue;
      found.push(...liveComponentFiles(path));
    } else if (entry.endsWith(".tsx")) {
      found.push(path);
    }
  }
  return found;
}

// No dotAll flag: `[^}]` and `\s` already cross the newlines in a grouped
// import, and the tsconfig target predates es2018.
const IMPORTS_TREMOR_BUTTON =
  /import\s*\{[^}]*\bButton\b[^}]*\}\s*from\s*["']@tremor\/react["']/;
const TREMOR_BUTTON_WITH_LOADING = /<Button\b[^>]*\bloading=/;

describe("Tremor's loading button", () => {
  const files = liveComponentFiles();

  it("finds the app's components", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("is never asked to render a loading state", () => {
    const offenders = files.filter((path) => {
      const source = readFileSync(path, "utf8");
      return (
        IMPORTS_TREMOR_BUTTON.test(source) &&
        TREMOR_BUTTON_WITH_LOADING.test(source)
      );
    });
    expect(offenders).toEqual([]);
  });

  it("is not handed a loading prop by LoadingButton either", () => {
    const source = readFileSync(join(SRC, "components/LoadingButton.tsx"), "utf8");
    expect(TREMOR_BUTTON_WITH_LOADING.test(source)).toBe(false);
    expect(source).toContain("aria-busy");
  });
});
