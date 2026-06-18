// Minimal no-op service worker so the PWA is installable.
// The other dev can add real caching strategies later.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
