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
- Caddy als TLS-Reverse-Proxy

## Request-Fluss

1. Client sendet `POST /live-location`
2. Middleware vergibt `request_id`, misst Laufzeit und prüft das Body-Limit
3. Bearer-Auth und optionales In-Memory-Rate-Limit greifen
4. Pydantic validiert den Payload
5. Storage speichert Request-Metadaten und einzelne Punkte
6. optional wird das Rohpayload in NDJSON auditiert
7. API antwortet mit `202 Accepted`

## Operator-Zugriff

- Session-Cookie nach Bearer-Login
- optional HTTP Basic Auth
- ohne Admin-Credentials lokal-only

## Kartenmodell

- `/dashboard/map` rendert nicht mehr aus rohen Punktelisten allein
- der Browser lädt stattdessen:
  - `GET /api/map-meta` für globale Kartenmetadaten
  - `GET /api/map-data` für viewport-basierte Layerdaten
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
- Multi-User-/Rollenmodell
- automatische Retention- oder Export-Jobs
