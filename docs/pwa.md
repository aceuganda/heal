# PWA: why it is paused, and what to use when we bring it back

Heal shipped as an installable PWA via `@ducanh2912/next-pwa`. That plugin is
gone as of the Next 16 upgrade. This note records what we lost, what still
works, and which option to pick when offline support becomes a requirement
rather than a nice-to-have.

---

## Why it was removed

**It was the single largest cost in the web build.** The plugin wrapped
`next.config.js` and ran a second full webpack pass to compile the service
worker. It was visible in the build log as a duplicated line:

```
✓ (pwa) Compiling for server...
✓ (pwa) Compiling for server...        <- the plugin's pass, not a repeated log
✓ (pwa) Compiling for client (static)...
```

**It was unmaintained.** Last publish was 10.2.9 in September 2024. The author
has since moved to Serwist (below) and treats `@ducanh2912/next-pwa` as
superseded.

**It blocked the Next upgrade.** The plugin is a webpack plugin. Next 16 builds
with Turbopack by default, and the compile dropped to ~3s once the plugin was
out of the way.

## What still works without it

Removing the service worker is not the same as removing installability.

| Capability | Status | Why |
|---|---|---|
| `public/manifest.json` | Kept | Referenced from `src/app/layout.tsx` metadata |
| Home-screen icons (192–512px) | Kept | In `public/`, listed in the manifest |
| Install on iOS Safari | Works | iOS never required a service worker |
| The `AddToHomeScreen` prompt | Works | `src/components/AddToHomeScreen/` sniffs the browser and shows instructions; it does not use `beforeinstallprompt` |
| **Offline / cached shell** | **Lost** | This was the service worker's whole job |
| **Chrome/Android native install prompt** | **Likely lost** | Chrome's installability criteria want a service worker with a fetch handler. The manual instruction prompt above still renders, so the path is degraded rather than gone. Worth confirming on a real Android device before assuming either way. |

For Heal's users the offline shell is the one that actually matters — a health
worker on an intermittent connection. That is the trigger for revisiting this,
not the install prompt.

## The kill switch — do not delete this yet

`web/public/sw.js` is hand-written and **is source**, despite the `sw.*` rule in
`web/.gitignore` (there is a `!public/sw.js` negation for exactly this reason).

Deleting the plugin stops us *generating* a service worker. It does nothing to
the worker already installed in a returning visitor's browser, which keeps
serving its precache — those users would be pinned to the last PWA build and
never see another deploy. Serving a replacement at the same `/sw.js` path takes
over, drops every cache, unregisters itself, and reloads open tabs.

It has no `fetch` handler, so it never intercepts a request while alive. Leave
it in place until returning visitors have plausibly all picked it up. Leaving it
forever is harmless: a browser with no worker registered never requests it.

---

## Options for bringing PWA back

### 1. Serwist — the direct successor (recommended if we want the plugin model)

`@serwist/next`. Same author as `@ducanh2912/next-pwa`, explicitly its
replacement. Actively maintained (9.5.12, published July 2026; a 10.x preview
line exists). Peer range is `next >= 14.0.0`, so Next 16 is in scope.

- **For:** closest thing to a drop-in; we keep a declarative Workbox-style
  config; someone else maintains the caching strategies.
- **Against:** re-introduces a build-time plugin, which is what we just removed.
  Verify it does not force the build back onto webpack before committing — that
  was the actual cost, not the service worker itself.
- **Check first:** whether the installed version supports Turbopack builds.

### 2. A hand-written service worker

Write `public/sw.js` properly and register it ourselves. We already own a
hand-written worker for the kill switch, so the mechanism is understood.

- **For:** zero build-time cost, zero plugin dependency, no third upgrade
  blocker the next time Next moves. We control exactly what is cached, which
  matters because Heal's chat responses are per-user and must *not* be cached.
- **Against:** we own cache invalidation and versioning, which is the part of
  service workers that actually bites.
- **Best if** all we want is an offline app shell plus static assets, and not
  offline chat history.

### 3. Workbox directly, as a build step

`workbox-cli` invoked from an npm script, generating the worker outside the Next
build entirely.

- **For:** Workbox's strategies without coupling to Next's bundler; survives
  future Next upgrades.
- **Against:** another build step to wire into the Dockerfile and CI.

### 4. Stay off PWA

The manifest already gives installability on iOS, which is a large share of the
target devices. If offline is not a near-term requirement, this option costs
nothing and blocks nothing.

**Recommendation:** option 4 until offline is an actual requirement, then
option 2 if the need is just an offline shell, or option 1 if we want cached
routes and background sync without writing them ourselves.

---

## Related state worth knowing

- **`npm run lint` is broken.** Next 16 removed the `next lint` command that the
  script calls. `eslint` and `eslint-config-next` were deliberately left alone;
  fixing this means moving to ESLint 9 flat config, which is its own task.
- **Capacitor versions are mismatched.** `@capacitor/cli` is on `^8.5.1` while
  `@capacitor/android`, `@capacitor/core`, and `@capacitor/ios` are on `^5.7.0`
  — a `npm audit fix --force` side effect. The mobile shell also has
  `webDir: '.next'` in `capacitor.config.ts`, which is not a static export
  directory, so the native build is unlikely to work as committed. Decide
  whether the mobile shell is live before spending anything on it.
- **React 19 is blocked by Tremor.** `@tremor/react` still pins `react: ^18.0.0`
  as of 3.18.7, and 32 files import it. Next 16 runs fine on React 18.2 (this is
  what we ship), so this is not urgent — but it is the thing to resolve before
  any React 19 move.
