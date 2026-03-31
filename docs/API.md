# API

## `GET /health`

Liveness-Check. Antwortet mit Prozessstatus und Storage-Grunddaten.

## `GET /readyz`

Readiness-Check. Antwortet mit `200`, wenn der Receiver Daten sicher schreiben kann, sonst `503`.

## `POST /live-location`

Nimmt Live-Location-Requests an.

### Erwartete Felder

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

## `GET /api/stats`

Operator-API mit:

- Gesamtanzahl Requests
- akzeptierte und fehlgeschlagene Requests
- Gesamtanzahl Punkte
- letzter Erfolg / letzter Fehler
- Punkte pro Tag
- Punkte pro Session

## `GET /api/points`

Liste gespeicherter Punkte, neueste zuerst.

### Query-Parameter

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
- `format=json|csv|ndjson`

## `GET /api/points/{id}`

Punktdetail.

## `GET /api/requests`

Requestliste mit optionalen Filtern:

- `date_from`
- `date_to`
- `time_from`
- `time_to`
- `session_id`
- `capture_mode`
- `source`
- `ingest_status`
- `search`
- `page`
- `page_size`

## `GET /api/requests/{request_id}`

Requestdetail inklusive Rohpayload, Bounding Box und gespeicherter Punkte.

## `GET /api/sessions`

Sessionliste mit Punktanzahl und erstem/letztem Punkt.

## `GET /api/sessions/{session_id}`

Sessiondetail mit zugeordneten Requests, Bounding Box und Zeitspanne.

## `GET /api/config-summary`

Masked operator summary of runtime config. Secrets bleiben maskiert.

## `GET /dashboard`

HTML-Ansicht fuer Operatoren.

## Scope-Hinweis

Diese API-Doku beschreibt nur den aktuell umgesetzten Receiver-Stand. Bewusst nicht Teil dieses Laufs:

- separate Admin-Session-Auth
- weitergehende Operator-Rollen
- geplante Export-/Retention-Jobs

Offene Folgepunkte stehen in [OPEN_ITEMS.md](OPEN_ITEMS.md).
