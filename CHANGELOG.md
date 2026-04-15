# Changelog

## 2026-04-15

### Added
- interaktive Echtzeit-Karte (`/dashboard/map`) mit Leaflet, CartoDB-Dark-Tiles und MarkerCluster
- Live-Punkt-Log direkt unter der Karte: scrollbare Echtzeit-Tabelle, Zeitstempel in `Europe/Berlin`
- Zeitraumfilter auf der Karte: 2min bis 30 Tage und gesamt (max. 2000 Punkte), mit localStorage-Persistenz
- Session-Filter per Dropdown, beschriftet mit Zeitstempelbereich der Session
- Auto-Follow: Karte folgt automatisch dem neuesten eingehenden Punkt (Zoom 18)
- Fit-Bounds: gesamten Track auf einmal anzeigen
- konfigurierbares Polling-Intervall: 2s / 3s / 5s (Standard) / 10s bis 5min
- GeoJSON-Export des aktuellen Karteninhalts, Copy-to-Clipboard für Koordinaten
- iOS-Vollbild-Fallback: `position:fixed; 100vw/100dvh` per ⛶-Button, da `requestFullscreen()` auf iOS nicht unterstützt wird
- einmaliger "Zum Home-Bildschirm"-Banner mit Anleitung (pro Session, schließbar)
- Punkte/min-Statistik basierend auf den letzten 100 Punkten
- vollständige deutsche Lokalisierung aller Dashboard-Seiten
- Session-Cookie-Auth für das Dashboard; nach Login Redirect auf `/dashboard/map`
- `POINTS_PAGE_SIZE_MAX` von 250 auf 2000 erhöht für vollständige Track-Darstellung

### Changed
- iOS-inspiriertes Dark-Design-System für alle Templates: OLED-Schwarz `#000000`, Mint-Akzent `#30D158`, semantische Farben (Blau, Orange, Lila, Rot, Teal), Glasmorphismus-Header (`backdrop-filter: blur(20px)`), Pill-Buttons, gerundete Karten
- CSS-Grid-Layout für die Kartenseite: 3-Spalten Desktop (≥1440px), 2-Spalten Tablet (768–1439px), 1-Spalte Mobile (<768px)
- Filter-Panel auf Mobile einklappbar via Toggle-Button
- Breakpoints vereinheitlicht: 768px und 1440px (vorher: 767/768px und 1400/1440px durchmischt)
- Leaflet `invalidateSize()` sofort beim Laden + ResizeObserver statt verzögertem Timeout
- Log-Zeitstempel auf `Europe/Berlin` via `Intl.DateTimeFormat` umgestellt
- Zeitraumfilter sendet UTC-Werte (korrekt, da `LOCAL_TIMEZONE=UTC` in DB)

### Fixed
- iPhone-Overflow: `min-width:0` + `overflow-x:hidden` auf allen CSS-Grid-Children (`app-shell`, `page-shell`, `panel`, `map-page-container`)
- Tabellen-`min-width:900px` auf `@media (min-width:1024px)` beschränkt (verhinderte horizontalen Overflow auf 375px-Screens)
- Panel-Padding von 4px auf 12px erhöht (war unlesbar auf Mobile)
- Sidebar nicht scrollbar auf `max-width:1024px` → `overflow-y:auto` ergänzt
- Map-Filter-Panel wurde unten abgeschnitten → `max-height: calc(100vh - …)` + `overflow-y:auto`
- `<script>`-Tag stand nach `</html>` (invalides HTML) → in `</body>` verschoben
- Log-Search-Input mit `width:200px` fest → `width:100%; max-width:200px`
- Zeitraumfilter-Bug durch Berlin-Zeit-Versuch verursacht → revertiert auf UTC (`toISOString().slice`)
- Spalte `Genauigkeit` im Live-Log auf Mobile ausgeblendet (`.log-col-accuracy`)
- Session-Select-Dropdown-Synchronisation bei leerem Default-Wert korrigiert

## 2026-04-13

### Added
- Session-Cookie-basierte Login-Seite für das Dashboard (`/login`), inkl. Logout
- `feat(auth)`: Template-Bug im Gemini-generierten Code behoben der Login-Redirect verhinderte
- vollständige Bedienungsanleitungen in `docs/WEBSEITE_BEDIENUNG.md` und `docs/WEBSEITE_TECHNISCH.md`
- Nutzer- und Betreuer-Anleitungen (`docs/USER_GUIDE.md`, `docs/MAINTAINER_GUIDE.md`)
- dedizierte Desktop- und Mobile-CSS-Dateien (`desktop.css`, `mobile.css`) neben `style.css`
- Homepage (`/`) mit vollständiger Übersicht und verifizierten Endpunkten
- Empty-State auf der Exporte-Seite verbessert

### Fixed
- `StorageError` lieferte JSON statt HTML → gibt jetzt korrekte HTML-Fehlerseite zurück
- temporäre Audit-Artefakte aus dem Repo entfernt
- Tippfehler in mehreren Templates und Dokumentationsdateien

### Changed
- Dokumentation umfassend überarbeitet und Formatierung bereinigt

## [2026-04-12]
### Security
- `storage.py`: Raw-Payload-NDJSON-Datei wird jetzt mit Modus 0o600 erstellt (vorher: umask-abhängig)
- `.env.example`: erklärender Kommentar zu ENABLE_RAW_PAYLOAD_NDJSON ergänzt

## 2026-03-31 (v0.5 — UI-Redesign)

### Changed
- vollstaendiges Redesign des Operator-Dashboards: neue Informationsarchitektur mit Global-Header-Strip, Alert-Strip, Status-Kacheln (tile grid), Next-Actions-Block, Quick-Actions-Bar und Context-Footer
- Navigation neu strukturiert nach Task-Orientierung: Overview / Daten / Betrieb & Sicherheit / Hilfe; Reihenfolge priorisiert Receiver-Betrieb vor Detail-Navigationsgruppen
- neue Startseite (Overview / Dashboard) zeigt 6 kompakte Status-Kacheln: Receiver, Security, Storage, System, Ingest-Volumen, Aktivitaet — je mit STATUS-Badge (OK/WARN/CRIT/INFO) und 2-4 wichtigen Kennzahlen
- jede Seite erhaelt konsistenten Global-Header (Host, Receiver-Status, Auth, Uptime, letzter Ingest, Version) und Context-Footer (Bind, Storage, Admin, Timezone)
- Alert-Strip ersetzt die bisherigen `notice`-Banner im Content-Bereich: gruen/gelb/rot semantisch je nach Receiver-Zustand
- Quick-Actions-Bar am Seitenende mit primaeren und sekundaeren Schnellwegen auf jeder Seite
- Farbsystem ueberarbeitet: semantisch (rot=crit, gelb=warn, gruen=ok, blau=info, grau=meta) statt zuvor dekorativ
- Live-Status, Aktivitaet, Security, Storage, System — alle Seiten auf neue Kachel/Metriken-Architektur umgestellt
- Detail-Seiten (Request, Session, Punkt) mit neuen Metric-Rows statt alter metric-grid compact
- Responsive-Breakpoints verbessert: kompakteres Portrait-Layout fuer Mobilgeraete / iPhone
- CSS komplett neu — kein harter Vollrahmen mehr, mehr Whitespace, kleinere Sidebar, konsistenteres Typografiesystem
- App-Version jetzt im Global-Header sichtbar
- Tests angepasst: Assertions auf geaenderte Texte (neue UI-Texte statt alter Panel-Überschriften)

## 2026-03-31

### Changed
- Receiver-Admin-UI als receiver-first Operator-Workspace neu strukturiert: Dashboard, Navigation, Statuskarten, Tabellen und Detailseiten wurden visuell und inhaltlich deutlich modernisiert, ohne die Kernfunktion zu aendern.
- die HTML-Oberflaeche fuehrt Daten-, Betriebs-, Sicherheits- und Systempfade jetzt ueber eine konsistente Hauptnavigation statt ueber ein einzelnes Minimal-Dashboard zusammen.
- die Operator-Sicht zeigt jetzt deutlich mehr direkte Receiver-Infos wie Uptime, Erfolgsquote, Fehlerrate, Requests/Punkte heute bzw. 24h/7d, Response-Code-Verteilung, Storage-Dateigroessen und letzte Warnhinweise.
- 4-Repo-Statusdokumentation ergaenzt: README beschreibt die Receiver-Rolle jetzt explizit als optionalen Self-Hosted-Baustein ohne Pflicht-Cloud und trennt frische Linux-Repo-Verifikation von der frueheren Live-Betriebspruefung.
- `docs/OPEN_ITEMS.md` fuehrt Token-Rotation und appseitige Testserver-/Testtoken-Defaults jetzt expliziter als offene Security-/Produktpunkte.
- neues timestamped Status-Audit `docs/AUDIT_RECEIVER_STATE_2026-03-31_08-48.md` dokumentiert den Receiver-Ist-Stand repo-wahr fuer diesen Lauf.

### Fixed
- confirmed and removed the runtime `HTTP 500` ingest failure caused by the old append-only storage path failing with `FileNotFoundError`
- hardened receiver startup so writable data and log directories are prepared before the app runs as `appuser`
- added explicit readiness handling so storage problems return `503` instead of an opaque `500`

### Added
- SQLite persistence for accepted and failed ingest requests plus individual GPS points
- optional NDJSON raw-payload audit trail
- legacy one-time import path for older `live-location.ndjson` request archives when booting into an empty database
- `GET /readyz`
- `GET /api/stats`
- `GET /api/points`
- `GET /api/points/{id}`
- `GET /api/requests`
- `GET /api/requests/{request_id}`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `GET /api/config-summary`
- neue HTML-Views fuer `/dashboard/live-status`, `/dashboard/activity`, `/dashboard/points`, `/dashboard/points/{point_id}`, `/dashboard/requests`, `/dashboard/sessions`, `/dashboard/exports`, `/dashboard/config`, `/dashboard/storage`, `/dashboard/security`, `/dashboard/system`, `/dashboard/troubleshooting` und `/dashboard/open-items`
- `GET /dashboard`, `/dashboard/requests/{request_id}` and `/dashboard/sessions/{session_id}`
- CSV, JSON and NDJSON export for filtered point lists
- operator-safe config summary with masked secrets
- structured request logging with `request_id`, path, status, timing and ingest metadata
- receiver tests for readiness, auth, validation, storage errors, unexpected errors, exports, dashboard rendering, navigation rendering and secret masking
- receiver architecture, API, operations, troubleshooting, security, data-model and app-store/privacy notes

### Changed
- `.env.example` now uses neutral placeholders instead of a baked-in public test host
- Docker Compose now renders without requiring a committed `.env`
- Caddy now emits JSON access logs and adds baseline security headers
- smoke checks now include `readyz` and optional operator-UI verification
- documentation now separates merge-ready receiver functionality from intentionally deferred hardening, auth, retention and app-side follow-up work
- `main` was re-checked after merge in the running server setup; no additional receiver-side changes were required from that verification

## 2026-03-20

### Added
- initial minimal FastAPI live-location receiver for `LocationHistory2GPX-iOS`
- `POST /live-location` with optional bearer auth, payload validation and append-only NDJSON persistence
- `GET /health` for smoke checks and container health status
- Docker Compose deployment for this host
- pytest coverage for health, auth success/failure, valid payload acceptance and invalid payload rejection
- deploy runbook, env example and curl/smoke test guidance

### Changed
- HTTPS was exposed via Caddy on a public host
- FastAPI backend was bound to `127.0.0.1:8080` on the host instead of a public `8080/tcp`
