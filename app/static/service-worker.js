// Minimaler Service Worker für die PWA-Installation ("Zum Home-Bildschirm
// hinzufügen" auf iOS/Android) — cached NUR sichere statische App-Assets
// (CSS, JavaScript, Manifest/Icon),
// NIEMALS API-Antworten, Live-Location-Ingest oder den WebSocket-Traffic,
// damit GPS-Live-Daten/Session-/Punktestatus immer aktuell bleiben.
//
// Muss aus dem Root-Scope ("/service-worker.js", nicht "/static/...")
// ausgeliefert werden, siehe app/main.py — sonst gilt der Scope nur für
// "/static/*" und Navigationen zu "/dashboard"/"/dashboard/map" würden
// nicht kontrolliert.
//
// CACHE_VERSION bei jeder Änderung an der gecachten Asset-Menge oder
// Cache-Strategie erhöhen. HTML-Navigationen werden absichtlich nicht
// gecacht: So können sessionabhängige oder veraltete Seiten keine
// Deployment-Probleme verursachen. Bei Offline-Navigationen gibt es nur den
// neutralen Fallback — siehe OFFLINE_HTML unten.
const CACHE_VERSION = "lh2gpx-shell-v2";

// Statische Assets, die für die Live-Karte unterwegs auch bei Empfangslücken
// verfügbar bleiben sollen. HTML-Seiten gehören ausdrücklich nicht hierher.
const SHELL_URLS = [
  "/static/tokens.css",
  "/static/css/app.css",
  "/static/css/map.css",
  "/static/vendor/maplibre-gl/maplibre-gl.js",
  "/static/vendor/maplibre-gl/maplibre-gl.css",
  "/static/vendor/dexie.js",
  "/static/js/map-page.js",
  "/static/manifest.json",
  "/static/apple-touch-icon.png",
];

// Pfade, die NIE aus dem Cache bedient werden dürfen — Live-/Ingest-/
// Steuerdaten. Bewusst als Prefix-Liste, damit neue /api/*-Endpunkte
// automatisch ausgenommen bleiben.
const NEVER_CACHE_PREFIXES = [
  "/api/",
  "/live-location",
  "/ws/map",
  "/health",
  "/readyz",
];

function isNeverCache(pathname) {
  return NEVER_CACHE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function isShellCacheable(pathname) {
  if (isNeverCache(pathname)) return false;
  return SHELL_URLS.includes(pathname) || pathname.startsWith("/static/vendor/maplibre-gl/");
}

function hasSensitiveCacheHeaders(response) {
  const cacheControl = response.headers.get("Cache-Control") || "";
  const vary = response.headers.get("Vary") || "";
  return (
    /(?:^|,)\s*(?:no-store|private)\b/i.test(cacheControl) ||
    /(?:^|,)\s*cookie\s*(?:,|$)/i.test(vary) ||
    response.headers.has("Set-Cookie") ||
    response.headers.has("WWW-Authenticate")
  );
}

function canCacheResponse(response) {
  // Nur erfolgreiche, gleich-origin Antworten aus dem eigenen Server cachen.
  // Opaque/CORS-Antworten und explizit private Antworten bleiben draußen.
  return response && response.ok && response.type === "basic" && !hasSensitiveCacheHeaders(response);
}

async function cacheShellAsset(cache, pathname) {
  try {
    const response = await fetch(new Request(pathname, {
      cache: "no-store",
      credentials: "same-origin",
    }));
    if (canCacheResponse(response)) await cache.put(pathname, response);
  } catch {
    // Einzelne fehlende Assets dürfen die Installation nicht verhindern.
  }
}

// Offline-Fallback für HTML-Navigationen ohne Netzwerk UND ohne Treffer im
// Shell-Cache (z.B. eine noch nie geladene Route). Design-Ton passend zum
// bestehenden iOS-Dark-Theme (Mint-Akzent #30D158, siehe app/static/css/app.css).
const OFFLINE_HTML = `<!doctype html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Keine Verbindung — LH2GPX Live Receiver</title>
<style>
  html,body{height:100%;margin:0;}
  body{
    display:flex;align-items:center;justify-content:center;
    background:#000;color:#fff;
    font-family:-apple-system,"SF Pro Text",system-ui,sans-serif;
    text-align:center;padding:24px;box-sizing:border-box;
  }
  .card{max-width:360px;}
  .glyph{font-size:2.4rem;margin-bottom:14px;}
  h1{font-size:1.15rem;margin:0 0 10px;color:#30D158;}
  p{font-size:0.92rem;line-height:1.5;color:rgba(255,255,255,0.65);margin:0 0 18px;}
  button{
    background:#30D158;color:#000;border:none;border-radius:10px;
    padding:10px 18px;font-size:0.9rem;font-weight:600;cursor:pointer;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="glyph">📡</div>
    <h1>Keine Verbindung</h1>
    <p>LH2GPX ist gerade offline erreichbar. Zeige den zuletzt bekannten Kartenstand, sobald wieder Empfang besteht — Live-Standortdaten werden automatisch nachgeladen.</p>
    <button onclick="location.reload()">Erneut versuchen</button>
  </div>
</body>
</html>`;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) =>
      Promise.all(SHELL_URLS.map((pathname) => cacheShellAsset(cache, pathname)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))
    );
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Nur gleich-origin Requests behandeln. Fremde Ressourcen und ihre
  // Antworten dürfen nicht in den lokalen App-Cache gelangen.
  if (!isSameOrigin(url)) return;

  // Live-/Ingest-/Steuerdaten NIE aus dem Cache bedienen.
  if (isNeverCache(url.pathname)) return;

  if (event.request.method !== "GET") return;

  const isNavigation = event.request.mode === "navigate";

  // Andere GET-Endpunkte bleiben vollständig beim Browser und werden weder
  // gecacht noch bei Fehlern durch Response.error() überschrieben.
  if (!isNavigation && !isShellCacheable(url.pathname)) return;

  // Navigationen sind network-only: Keine HTML-Seite wird aus dem Cache
  // bedient. Bei Offline-Navigationen erscheint der neutrale Fallback.
  // Statische Assets sind network-first und fallen nur bei echtem
  // Netzwerkfehler auf den versionierten Asset-Cache zurück.
  event.respondWith(
    fetch(new Request(event.request, { cache: "no-store" }))
      .then((response) => {
        if (!isNavigation && canCacheResponse(response) && isShellCacheable(url.pathname)) {
          const copy = response.clone();
          caches.open(CACHE_VERSION)
            .then((cache) => cache.put(event.request, copy))
            .catch(() => {
              // Quota-/Cachefehler dürfen die aktuelle Netzwerkantwort nicht
              // beeinflussen.
            });
        }
        return response;
      })
      .catch(() =>
        caches.open(CACHE_VERSION).then((cache) => cache.match(event.request)).then((cached) => {
          if (cached) return cached;
          if (isNavigation) {
            return new Response(OFFLINE_HTML, {
              status: 200,
              headers: {
                "Cache-Control": "no-store",
                "Content-Type": "text/html; charset=utf-8",
                "X-Content-Type-Options": "nosniff",
              },
            });
          }
          return Response.error();
        })
      )
  );
});
