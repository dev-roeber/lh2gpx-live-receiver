# Operations

## Regelbetrieb

- `systemctl --user status lh2gpx-live-receiver.service`
- `journalctl --user -u lh2gpx-live-receiver.service --since today`
- `curl http://127.0.0.1:8082/readyz`
- `./scripts/smoke-test.sh`

## Wichtige Defaults

- `REQUEST_BODY_MAX_BYTES=262144`
- `POINTS_PAGE_SIZE_DEFAULT=50`
- `POINTS_PAGE_SIZE_MAX=2000`
- `RATE_LIMIT_REQUESTS_PER_MINUTE=0`
- Karten-Fallback-Limit zusätzlich intern auf `20000` gedeckelt

## Laufende Instanz

- öffentlich den zentralen Dashboard-Proxy verwenden: `https://devroeber.tail71a8bc.ts.net/receiver/dashboard`
- `PUBLIC_BASE_URL` ist für alternative Standalone-/Reverse-Proxy-Deployments gedacht und entspricht nicht automatisch der öffentlichen Dawarich-Adresse
- bei `sslip.io`-Deployments ist die rohe IP kein sauberer TLS-Einstieg

## Backups

- `DATA_DIR/receiver.sqlite3`
- optional `RAW_PAYLOAD_NDJSON_PATH`
- `compose.yaml`
- lokale `.env`

## Restore

1. Receiver stoppen
2. SQLite- und optionale NDJSON-Dateien wiederherstellen
3. den verwendeten Betriebsmodus starten (`systemctl --user restart lh2gpx-live-receiver.service` oder optional `docker compose up -d`)
4. `readyz`, `/health` und Dashboard prüfen

## Wartung

- SQLite läuft im WAL-Modus
- `VACUUM` nur im Wartungsfenster
- Raw-Payload-Datei nur bei echtem Debug-Bedarf aktiv halten
- Kartenlast primär über `/api/map-data`, `/api/map-meta`, `/api/timeline`, `/api/timeline-preview` und `/ws/map` bewerten; `/api/points` ist nicht mehr der primäre Kartenpfad
- räumliche Hot-Paths nutzen aktuell:
  - `gps_points_rtree`
  - tile-basierte Prefilter (`tile_z10_*`, `tile_z14_*`)
- ingest-nahe Vorberechnung ist bereits aktiv für:
  - `point_rollups`
  - `timeline_day_markers`

## Validierungsskripte

- `scripts/validate-professional.sh` liest optional `.env` aus dem Repo
- destructive Ingest-Checks nur bewusst mit gültigem Token ausführen
