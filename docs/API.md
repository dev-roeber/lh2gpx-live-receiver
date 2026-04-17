# API

## Basis

- JSON-API für Ingest, Monitoring und Operatoren
- HTML-Dashboard unter `/dashboard/*`

## `GET /health`

- Liveness-Check
- liefert Prozessstatus und Storage-Grunddaten

## `GET /readyz`

- Readiness-Check
- `200`, wenn der Receiver sicher schreiben kann
- `503`, wenn Storage oder Dateisystem nicht bereit sind

## `POST /live-location`

- Ingest-Endpunkt für Live-Location-Uploads
- erwartete Felder:
  - `source`
  - `sessionID`
  - `captureMode`
  - `sentAt`
  - `points[]`
  - `points[].latitude`
  - `points[].longitude`
  - `points[].timestamp`
  - `points[].horizontalAccuracyM`

### Statuscodes

- `202` accepted
- `401` missing or invalid bearer token
- `413` request body too large
- `422` payload validation failed
- `429` rate limit exceeded
- `503` storage unavailable
- `500` unexpected internal error

## Operator-API

- `GET /api/stats`
- `GET /api/live-summary`
- `GET /api/points`
- `GET /api/points/{id}`
- `GET /api/requests`
- `GET /api/requests/{request_id}`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`
- `GET /api/config-summary`
- `POST /api/settings`
- `POST /api/import`
- `GET /api/import/status/{task_id}`
- `POST /api/storage/vacuum`

## Punkte- und Request-Filter

- `date_from`
- `date_to`
- `time_from`
- `time_to`
- `session_id`
- `capture_mode`
- `source`
- `search`
- `page`
- `page_size`

Zusätzlich für Requests:

- `ingest_status`

Zusätzlich für Punkte:

- `format=json|csv|ndjson`

## Import

- unterstützte Dateitypen:
  - `json`
  - `gpx`
  - `kml`
  - `kmz`
  - `geojson`
  - `csv`
  - `zip`
- Dedupe erfolgt über `timestamp + latitude + longitude`

## Dashboard-Routen

- `/dashboard`
- `/dashboard/map`
- `/dashboard/import`
- `/dashboard/live-status`
- `/dashboard/activity`
- `/dashboard/points`
- `/dashboard/points/{id}`
- `/dashboard/requests`
- `/dashboard/requests/{request_id}`
- `/dashboard/sessions`
- `/dashboard/sessions/{session_id}`
- `/dashboard/exports`
- `/dashboard/config`
- `/dashboard/storage`
- `/dashboard/security`
- `/dashboard/system`
- `/dashboard/troubleshooting`
- `/dashboard/open-items`

## Zugriffsschutz

- Ingest: Bearer-Token
- Dashboard:
  - signierter Session-Cookie nach Bearer-Login
  - optional HTTP Basic Auth
  - ohne Admin-Credentials lokal-only
