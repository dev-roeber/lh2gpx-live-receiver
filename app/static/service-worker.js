// Minimaler Service Worker für die PWA-Installation ("Zum Home-Bildschirm
// hinzufügen" auf iOS/Android) — cached NUR die statische App-Shell
// (Dashboard/Karten-Seiten, CSS, MapLibre-Vendor-Assets, map-page.js),
// NIEMALS API-Antworten, Live-Location-Ingest oder den WebSocket-Traffic,
// damit GPS-Live-Daten/Session-/Punktestatus immer aktuell bleiben.
//
// Muss aus dem Root-Scope ("/service-worker.js", nicht "/static/...")
// ausgeliefert werden, siehe app/main.py — sonst gilt der Scope nur für
// "/static/*" und Navigationen zu "/dashboard"/"/dashboard/map" würden
// nicht kontrolliert.
//
// CACHE_VERSION nur erhöhen, wenn sich die Shell-Cache-Strategie selbst
// ändert. App-spezifisch (LH2GPX hat die höchste PWA-Priorität, da primär
// mobil unterwegs für Live-GPS-Tracking genutzt): zusätzlich eine kleine
// Offline-Fallback-Seite für HTML-Navigationen, wenn weder Netzwerk noch
// Cache greifen (z.B. Erstaufruf ohne Empfang) — siehe OFFLINE_HTML unten.
const CACHE_VERSION = "lh2gpx-shell-v1";

// App-Shell: Seiten + Assets, die für die Live-Karte unterwegs auch bei
// Empfangslücken nutzbar bleiben sollen.
const SHELL_URLS = [
  "/dashboard",
  "/dashboard/map",
  "/static/tokens.css",
  "/static/css/app.css",
  "/static/css/map.css",
  "/static/vendor/maplibre-gl/maplibre-gl.js",
  "/static/vendor/maplibre-gl/maplibre-gl.css",
  "/static/js/map-page.js",
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

function isShellCacheable(pathname) {
  if (isNeverCache(pathname)) return false;
  return (
    SHELL_URLS.includes(pathname) ||
    pathname.startsWith("/static/vendor/maplibre-gl/") ||
    pathname === "/static/tokens.css" ||
    pathname === "/static/css/app.css" ||
    pathname === "/static/css/map.css" ||
    pathname === "/static/js/map-page.js"
  );
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
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_URLS)).catch(() => {
      // Erstinstallation darf nicht am Netzwerk scheitern (z.B. Server
      // kurzzeitig nicht erreichbar) — Service Worker installiert sich
      // trotzdem, füllt den Cache beim nächsten erfolgreichen Fetch nach.
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Live-/Ingest-/Steuerdaten NIE aus dem Cache bedienen.
  if (isNeverCache(url.pathname)) return;

  if (event.request.method !== "GET") return;

  const isNavigation = event.request.mode === "navigate";

  // Network-first mit Cache-Fallback: online immer die aktuelle Version
  // holen (und den Shell-Cache dabei auffrischen), nur bei Netzwerkfehler
  // (offline) auf die zuletzt bekannte Version zurückfallen. Schlägt auch
  // das fehl (z.B. Route nie zuvor besucht) und es handelt sich um eine
  // HTML-Navigation, wird die Offline-Fallback-Seite gezeigt.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && isShellCacheable(url.pathname)) {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => {
          if (cached) return cached;
          if (isNavigation) {
            return new Response(OFFLINE_HTML, {
              status: 200,
              headers: { "Content-Type": "text/html; charset=utf-8" },
            });
          }
          return Response.error();
        })
      )
  );
});
