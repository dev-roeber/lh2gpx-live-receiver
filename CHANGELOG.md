# Changelog

## 2026-03-31

### Changed
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
- `GET /dashboard`, `/dashboard/requests/{request_id}` and `/dashboard/sessions/{session_id}`
- CSV, JSON and NDJSON export for filtered point lists
- operator-safe config summary with masked secrets
- structured request logging with `request_id`, path, status, timing and ingest metadata
- receiver tests for readiness, auth, validation, storage errors, unexpected errors, exports, dashboard rendering and secret masking
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
