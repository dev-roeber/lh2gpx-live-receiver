# Deploy Runbook

Dieses Runbook beschreibt nur den Receiver-/Serverbetrieb. App, Wrapper und lokale Standortdateien sind bewusst nicht Teil dieses Schritts.

## Voraussetzungen

- Docker und `docker compose`
- Port `80/tcp` und `443/tcp` oeffenbar fuer den Reverse-Proxy
- eine lokale `.env` mit nicht versionierten Werten

## Erstes Setup

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
cp .env.example .env
mkdir -p data logs
docker compose build
docker compose up -d
```

## Pflichtchecks nach dem Start

```bash
docker compose ps
docker compose logs --tail=200
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/readyz
./scripts/smoke-test.sh
```

## Update-Deploy

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=200
```

## Datenverzeichnis

- SQLite: `DATA_DIR/receiver.sqlite3`
- optionales Rohpayload-NDJSON: `RAW_PAYLOAD_NDJSON_PATH`
- Legacy-Importquelle bei leerer DB: `LEGACY_REQUEST_NDJSON_PATH`

Das Datenverzeichnis ist bind-gemountet und damit hostseitig direkt sicherbar.

## Dashboard-Zugriff

- ohne `ADMIN_USERNAME` und `ADMIN_PASSWORD`:
  - Dashboard ist nur lokal erreichbar
- mit gesetzten Credentials:
  - Dashboard und API sind zusaetzlich ueber HTTP Basic Auth geschuetzt

## Sichere Defaults

- keine versionierte produktive Hostvorgabe
- kein versionierter Bearer-Token
- keine Klartext-Anzeige von Secrets in API oder UI

## Rollback

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
docker compose down
git checkout <bekannter-commit>
docker compose build
docker compose up -d
```

Wenn die Datenbasis erhalten bleiben soll, `./data` nicht loeschen.
