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
- `GET /api/map-data`
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

- `format=json|csv|ndjson|geojson`

## `GET /api/map-data`

- liefert ein serverseitig vorbereitetes Kartenmodell für `/dashboard/map`
- reduziert Client-Arbeit für mobile Geräte deutlich, weil Layer nicht mehr im Browser aus Rohpunkten zusammengesetzt werden
- unterstützt dieselben Grundfilter wie `GET /api/points` für:
  - `date_from`
  - `date_to`
  - `session_id`
  - `page_size`
- zusätzliche Layer- und Tuning-Parameter:
  - `zoom`
  - `route_time_gap_min`
  - `route_dist_gap_m`
  - `stop_min_duration_min`
  - `stop_radius_m`
  - `include_points`
  - `include_heatmap`
  - `include_polyline`
  - `include_accuracy`
  - `include_labels`
  - `include_speed`
  - `include_stops`
  - `include_daytrack`
  - `include_snap`
- Antwort enthält:
  - `meta`
  - `stats`
  - `layers`
  - `logItems`
- `ETag`/`304` wird wie bei `GET /api/points` unterstützt

## Import

- unterstützte Dateitypen:
  - `json`
  - `gpx`
  - `kml`
  - `kmz`
  - `geojson`
  - `geo.json`
  - `csv`
  - `zip`
- Dedupe erfolgt über `timestamp + latitude + longitude`
- Task-Status:
  - `queued`
  - `parsing`
  - `inserting`
  - `done`
  - `error`

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
