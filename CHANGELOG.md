# Changelog

## 2026-03-31 (v0.5 — UI-Redesign)

### Changed
- vollstaendiges Redesign des Operator-Dashboards: neue Informationsarchitektur mit Global-Header-Strip, Alert-Strip, Status-Kacheln (tile grid), Next-Actions-Block, Quick-Actions-Bar und Context-Footer
- Navigation neu strukturiert nach Task-Orientierung: Overview / Daten / Betrieb &amp; Sicherheit / Hilfe; Reihenfolge priorisiert Receiver-Betrieb vor Detail-Navigationsgruppen
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
- Tests angepasst: Assertions auf geaenderte Texte (neue UI-Texte statt alter Panel-Ueberschriften)

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
