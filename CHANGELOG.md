# Changelog

## 2026-03-20

### Added
- initial minimal FastAPI live-location receiver for `LocationHistory2GPX-iOS`
- `POST /live-location` with optional bearer auth, payload validation and append-only NDJSON persistence
- `GET /health` for smoke checks and container health status
- Docker Compose deployment for this host
- pytest coverage for health, auth success/failure, valid payload acceptance and invalid payload rejection
- deploy runbook, env example and curl/smoke test guidance

### Changed
- HTTPS is now exposed via Caddy on `https://178-104-51-78.sslip.io`
- FastAPI backend is now bound to `127.0.0.1:8080` on the host instead of a public `8080/tcp`
- runbook and README now document the HTTPS-first deployment state
