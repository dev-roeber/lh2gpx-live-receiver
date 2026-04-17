# Webseite – Technisch

## Templates

- `base.html` – Grundlayout und Navigation
- `dashboard.html` – Übersicht
- `map.html` – Live-Karte
- `import.html` – Dateiimport und Session-Löschung
- `points.html`, `requests.html`, `sessions.html` – Tabellenansichten
- Detailseiten für Punkte, Requests und Sessions

## Wichtige Routen

- `GET /login`
- `POST /login`
- `GET /logout`
- `GET /dashboard`
- `GET /dashboard/map`
- `GET /dashboard/import`
- `GET /dashboard/points`
- `GET /dashboard/requests`
- `GET /dashboard/sessions`

## Kontextmodell

- alle Dashboard-Routen nutzen `_base_template_context()`
- Snapshot-Daten kommen aus `_dashboard_snapshot()`
- Punkte- und Request-Views liefern auch im Fehlerfall strukturkompatible Leerpayloads

## Auth-Modell

- `_require_admin_access()` akzeptiert:
  - validen Session-Cookie
  - optional HTTP Basic Auth
  - lokal-only Zugriff ohne Admin-Credentials

## Settings-Hot-Reload

- `POST /api/settings` baut Storage und Rate-Limiter neu auf
- Template-Zeitzonenformatierung wird aktualisiert
- Request-Body-Limit wird pro Request aus den aktuellen Settings gelesen

## Import-Modell

- asynchroner Import-Task
- Dedupe innerhalb der Datei und gegen die Datenbank
- Schlüsselkombination: `point_timestamp_utc + latitude + longitude`
