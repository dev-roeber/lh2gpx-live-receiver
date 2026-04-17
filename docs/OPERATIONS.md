# Operations

## Regelbetrieb

- `docker compose ps`
- `docker compose logs --tail=200`
- `curl http://127.0.0.1:8080/readyz`
- `./scripts/smoke-test.sh`

## Wichtige Defaults

- `REQUEST_BODY_MAX_BYTES=262144`
- `POINTS_PAGE_SIZE_DEFAULT=50`
- `POINTS_PAGE_SIZE_MAX=2000`
- `RATE_LIMIT_REQUESTS_PER_MINUTE=0`

## Laufende Instanz

- öffentlich immer den konfigurierten Hostnamen unter `PUBLIC_BASE_URL` verwenden
- bei `sslip.io`-Deployments ist die rohe IP kein sauberer TLS-Einstieg

## Backups

- `DATA_DIR/receiver.sqlite3`
- optional `RAW_PAYLOAD_NDJSON_PATH`
- `compose.yaml`
- lokale `.env`

## Restore

1. Receiver stoppen
2. SQLite- und optionale NDJSON-Dateien wiederherstellen
3. `docker compose up -d`
4. `readyz`, `/health` und Dashboard prüfen

## Wartung

- SQLite läuft im WAL-Modus
- `VACUUM` nur im Wartungsfenster
- Raw-Payload-Datei nur bei echtem Debug-Bedarf aktiv halten

## Validierungsskripte

- `scripts/validate-professional.sh` liest optional `.env` aus dem Repo
- destructive Ingest-Checks nur bewusst mit gültigem Token ausführen
