// Kill switch for the retired next-pwa service worker.
//
// Deleting the plugin stops us GENERATING a service worker; it does not remove
// the one already installed in a returning visitor's browser. That worker keeps
// serving its precache, so those users would stay pinned to the last PWA build
// and never see another deploy.
//
// Serving this file at the same /sw.js path replaces the old worker with one
// that drops every cache, unregisters itself, and reloads open tabs onto the
// network. It has no fetch handler, so it never intercepts a request while it
// is alive.
//
// Safe to delete once returning visitors have had time to pick it up -- or
// simply left in place, since a browser that never had a worker registered
// never requests this file. See docs/pwa.md.

self.addEventListener("install", () => {
  // Do not wait for existing tabs to close before taking over.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));

      await self.registration.unregister();

      // Tabs currently controlled by the old worker are still showing precached
      // markup. Navigating them re-fetches from the network, now uncontrolled.
      const clients = await self.clients.matchAll({ type: "window" });
      for (const client of clients) {
        client.navigate(client.url);
      }
    })()
  );
});
