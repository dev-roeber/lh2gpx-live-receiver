# Changelog

## 2026-03-20

### Added
- initial minimal FastAPI live-location receiver for `LocationHistory2GPX-iOS`
- `POST /live-location` with optional bearer auth, payload validation and append-only NDJSON persistence
- `GET /health` for smoke checks and container health status
- Docker Compose deployment for this host, including direct port exposure on `8080`
- pytest coverage for health, auth success/failure, valid payload acceptance and invalid payload rejection
- deploy runbook, env example and curl/smoke test guidance

