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
- `GET /api/map-meta`
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
- reduziert Client-Arbeit deutlich, weil Layer nicht mehr primär im Browser aus Rohpunkten zusammengesetzt werden
- Grundfilter:
  - `date_from`
  - `date_to`
  - `session_id`
- zusätzliche Karten-/Refresh-Parameter:
  - `bbox`
  - `page_size` (nur Fallback, wenn noch kein Viewport verfügbar ist)
  - `log_limit`
  - `latest_known_ts`
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
  - `processing`
- `ETag`/`304` wird wie bei `GET /api/points` unterstützt
- bei unverändertem Viewport und unverändertem Datenstand antwortet der Server zusätzlich mit `304` und `X-Map-Delta: noop`
- bei echtem Delta kann `meta.deltaMode=true` gesetzt sein; dann enthält die Antwort ein `delta`-Objekt mit inkrementellen Punkt-/Log-Ergänzungen und gezielten Layer-Replacements

## `GET /api/map-meta`

- globaler Metapfad für `/dashboard/map`
- liefert:
  - `meta.totalPoints`
  - `meta.firstPointTsUtc`
  - `meta.lastPointTsUtc`
  - `meta.boundingBox`
  - `processing`
- wird für globale Statistik, `Fit Bounds = Gesamt` und die Verarbeitungsanzeige verwendet
- unterstützt `ETag`/`304`

## `GET /ws/map`

- WebSocket-Endpunkt für Karten-Clients
- sendet bei neuem Ingest `{"type":"new_location","sessionId":"..."}` an verbundene Browser
- dient als Echtzeit-Hinweis für die Kartenansicht; ersetzt den konfigurierbaren Polling-Pfad nicht vollständig

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
- `POST /api/import` antwortet direkt mit:
  - `ok`
  - `task_id`
  - `filename`
  - `file_size_bytes`
- `GET /api/import/status/{task_id}` liefert zusätzlich strukturierte Serverdaten:
  - `filename`
  - `file_size_bytes`
  - `detected_format`
  - `warnings`
  - `error_category`
  - `metrics.rawPoints`
  - `metrics.invalidRows`
  - `metrics.dedupedInFile`
  - `metrics.alreadyExisting`
  - `metrics.inserted`
  - `metrics.skippedTotal`
  - `metrics.firstTimestampUtc`
  - `metrics.lastTimestampUtc`
  - `metrics.parseDurationMs`
  - `metrics.insertDurationMs`
  - `metrics.totalDurationMs`
  - `metrics.archiveEntriesTotal`
  - `metrics.archiveEntriesUsed`
  - `metrics.archiveEntriesFailed`

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
