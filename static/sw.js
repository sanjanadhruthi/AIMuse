/* =========================================================
   AIMuse — service worker (makes AIMuse installable)
   =========================================================
   Deliberately simple and SAFE for a site that changes often:

   - Everything goes to the network first, so a new push is
     always seen right away (no "stuck on an old version").
   - Only if the phone is offline does the app fall back to a
     saved copy of the page, plus a short "you're offline" note,
     instead of the browser's dinosaur.

   Served from /sw.js (see app.py) so it covers the whole site.
   Bump VERSION to clear old saved copies.
   ========================================================= */

const VERSION = "aimuse-v1";

const OFFLINE_PAGE = "/";

self.addEventListener("install", (event) => {

    event.waitUntil(
        caches.open(VERSION)
            .then((cache) => cache.add(OFFLINE_PAGE))
            .catch(() => { /* offline during install: fine */ })
    );

    self.skipWaiting();
});

self.addEventListener("activate", (event) => {

    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key)))
        )
    );

    self.clients.claim();
});

self.addEventListener("fetch", (event) => {

    const request = event.request;

    // Only page loads are handled; music, videos, the API and
    // YouTube all go straight to the network as usual.
    if (request.mode !== "navigate") return;

    event.respondWith(
        fetch(request)
            .then((response) => {
                const copy = response.clone();
                caches.open(VERSION).then((cache) => cache.put(OFFLINE_PAGE, copy));
                return response;
            })
            .catch(() =>
                caches.match(OFFLINE_PAGE).then((saved) =>
                    saved || new Response(
                        "<h1 style='font-family:sans-serif;text-align:center;margin-top:30vh'>" +
                        "You're offline — AIMuse needs the internet for music 🌙</h1>",
                        { headers: { "Content-Type": "text/html; charset=utf-8" } }
                    )
                )
            )
    );
});