# Architecture

## Ziel

- optionaler Self-Hosted-Receiver für Live-Location-Uploads aus der App
- lokale Speicherung, Diagnose, Export und Operator-Sicht ohne externe Datenbank

## Bausteine

- FastAPI-App
- SQLite für Requests und GPS-Punkte
- optionales NDJSON-Audit für Rohpayloads
- serverseitig gerenderte Operator-UI
- MapLibre-basierte Operator-Karte mit serverseitiger Layer-Aufbereitung für `/dashboard/map`
- optional Caddy-Reverse-Proxy im Docker-Compose-Deployment
- produktiver Serverbetrieb: systemd-User-Service hinter Tailscale Funnel

## Request-Fluss

1. Client sendet `POST /live-location`
2. Middleware vergibt `request_id`, misst Laufzeit und prüft das Body-Limit
3. Bearer-Auth und optionales In-Memory-Rate-Limit greifen
4. Pydantic validiert den Payload
5. Storage speichert Request-Metadaten und einzelne Punkte
6. optional wird das Rohpayload in NDJSON auditiert
7. API antwortet mit `202 Accepted`

## Operator-Zugriff

- zentrale Dashboard-Session aus `~/services/auth/sessions.db`
- Cookie-Name: `ytdl_session` (gemeinsam mit Dashboard und ytdl-webui)
- nicht authentifizierte HTML-Aufrufe werden zur zentralen Dashboard-Loginseite weitergeleitet
- eine separate Receiver-Anmeldung ist im produktiven Setup deaktiviert
- der Ingest bleibt unabhängig davon per Bearer-Token geschützt

## Kartenmodell

- `/dashboard/map` rendert nicht mehr aus rohen Punktelisten allein
- der Browser lädt stattdessen:
  - `GET /api/map-meta` für globale Kartenmetadaten
  - `GET /api/map-data` für viewport-basierte Layerdaten
  - `GET /api/timeline` für leichte Timeline-Daten
  - `GET /api/timeline-preview` für Scrubbing-/Replay-Vorschau
- der Server bereitet daraus vor:
  - Punktlayer
  - Heatmap-Aggregate
  - vereinfachte Track-Polylinien
  - Geschwindigkeitssegmente
  - Stop-Erkennung
  - Tages-Tracks
  - optionalen Straßen-Snap
- der Browser hält zusätzlich einen lokalen IndexedDB-Mirror bereits geladener Punkte
- Live-Updates laufen hybrid:
  - WebSocket `/ws/map` signalisiert neue Daten
  - Polling bleibt als konfigurierbarer Refresh-Pfad aktiv
  - `latest_known_ts` und `ETag` vermeiden unnötige Vollantworten
  - echte Deltas ergänzen Punkte und Logs inkrementell
- ingest-nahe Vorberechnung entlastet den Request-Pfad bereits für:
  - globale und Session-Zusammenfassungen in `point_rollups`
  - Timeline-Day-Marker in `timeline_day_markers`
  - tile-basierte Raumspalten auf `gps_points`
- räumliche Kartenabfragen nutzen aktuell:
  - SQLite-RTree `gps_points_rtree`
  - zusätzliche Tile-Prefilter über `tile_z10_*` und `tile_z14_*`
- Ziel:
  - kleinere Payloads
  - weniger Client-CPU
  - konsistentere Darstellung auf mobilen Geräten
  - stabilerer Live-Betrieb bei großen Zeiträumen

## Hot-Reload

- `POST /api/settings` lädt unterstützte Runtime-Settings neu
- neu verdrahtet werden:
  - `app.state.settings`
  - `app.state.storage`
  - `app.state.rate_limiter`
  - Session-Signing-Key
  - Template-Zeitzonenformatierung
  - Request-Body-Limit via Request-Zeit-Lookup

## Import-Dedupe

- innerhalb der Datei: Dedupe über `timestamp + latitude + longitude`
- gegen die Datenbank: gleiche Triple-Kombination wird übersprungen

## Bewusst nicht umgesetzt

- persistentes Rate-Limit-Backend
- externes Migrationsframework
- eigene Multi-User-/Rollenverwaltung im Receiver (Rollen kommen aus dem zentralen Dashboard)
- automatische Retention- oder Export-Jobs
