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
- die Kartenansicht lädt ihr Arbeitsmodell über `GET /api/map-data`

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
- Frontend-Polling über `GET /api/import/status/{task_id}`
- Datei-Picker in `import.html` ist für Mobile Safari als echter Overlay-Input verdrahtet statt über einen programmgesteuerten Klick auf einen versteckten Input
- Parserpfad liefert über `parse_file_report(...)` strukturierte Metadaten statt nur Punktlisten
- Statusdaten enthalten:
  - Dateiname, Dateigröße und erkanntes Format
  - Warnungen und Fehlerkategorie
  - Rohpunkte, ungültige Zeilen, Datei-Dedupe und DB-Dedupe
  - erste/letzte Zeitstempel
  - Parse-, Insert- und Gesamtdauer
  - ZIP-spezifische Archivmetriken
- `storage.import_points(...)` gibt dafür ein erweitertes Ergebnisobjekt zurück statt nur `inserted/skipped`
- Tests nutzen optional `app.state.inline_import_tasks = True`, damit Import-Tasks im Testpfad deterministisch inline abgeschlossen werden

## Kartenmodell `/dashboard/map`

- `map.html` berechnet Layer nicht mehr primär aus `/api/points`
- der Browser fragt `GET /api/map-data` mit Filter- und Layer-Flags ab
- serverseitig vorbereitet werden:
  - Punkte
  - Heatmap-Zellen
  - Polylinien, bevorzugt mit serverseitig gesnappter Straßen-Geometrie
  - Genauigkeitskreise
  - Geschwindigkeitssegmente
  - Stops
  - Tages-Tracks
  - optionaler OSRM-Snap
- GeoJSON-Export nutzt das aktuell geladene Kartenmodell statt blind den gesamten Datenbestand zu exportieren
- Kartensteuerung ist nicht mehr als untere Quick-Bar umgesetzt, sondern als separates Dropdown-Menü oberhalb des Layer-Menüs
- Vollbildlayout wird über einen gemeinsamen Layoutpfad für nativen Fullscreen und CSS-Fallback synchronisiert
