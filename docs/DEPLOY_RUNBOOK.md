# Deploy Runbook

Dieses Runbook beschreibt nur den Receiver-/Serverbetrieb. App, Wrapper und lokale Standortdateien sind bewusst nicht Teil dieses Schritts.

## Voraussetzungen

- Docker und `docker compose`
- Port `80/tcp` und `443/tcp` offenbar für den Reverse-Proxy
- eine lokale `.env` mit nicht versionierten Werten

## Erstes Setup

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
cp .env.example .env
mkdir -p data logs
docker compose build
docker compose up -d
```

Hinweis zum NDJSON-Fix:

- neue `raw-payloads.ndjson`-Dateien werden im aktuellen Stand mit `0600` angelegt
- bereits vorhandene Dateien erben diese Rechte nicht nachtraeglich; Altbestaende müssen bei Bedarf separat geprueft oder operativ gehaertet werden

## Pflichtchecks nach dem Start

```bash
docker compose ps
docker compose logs --tail=200
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/readyz
./scripts/smoke-test.sh
```

## Post-merge verification auf `main`

Nach dem finalen Merge wurde `main` noch einmal direkt im laufenden Setup geprueft mit:

- `docker compose pull`
- `docker compose build`
- `docker compose up -d`
- `docker compose ps`
- `./scripts/smoke-test.sh`

Ergebnis:

- Receiver und Caddy liefen weiter sauber
- `health` und `readyz` blieben erfolgreich
- Live-Ingest, Dashboard und Punkteliste blieben funktionsfähig
- aus diesem Check war kein weiterer Receiver-Commit nötig

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
Der `0600`-Fix greift nur beim Anlegen neuer Raw-Payload-Dateien; bestehende Dateien werden nicht automatisch umgestellt.

## Dashboard-Zugriff

- ohne `ADMIN_USERNAME` und `ADMIN_PASSWORD`:
  - Dashboard ist nur lokal erreichbar
- mit gesetzten Credentials:
  - Dashboard und API sind zusätzlich über HTTP Basic Auth geschützt

## Sichere Defaults

- keine versionierte produktive Hostvorgabe
- kein versionierter Bearer-Token
- keine Klartext-Anzeige von Secrets in API oder UI
- weitergehende Produktionshaertung wie separate Admin-Auth, Retention-Automatisierung oder Job-Scheduling ist bewusst nicht Teil dieses Laufs

## Rollback

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
docker compose down
git checkout <bekannter-commit>
docker compose build
docker compose up -d
```

Wenn die Datenbasis erhalten bleiben soll, `./data` nicht löschen.

## Bewusst verschobene Folgearbeit

Vor einem breiteren produktiven Betrieb weiterhin offen:

- separate Admin-Authentifizierung statt nur Local-only-/Basic-Auth-Modell
- formalisierte Backup-/Restore-Automatisierung
- automatische Retention-/Export-Jobs
- finaler App-/Wrapper-Abgleich außerhalb dieses Repos
- Härtung bereits existierender Raw-Payload- oder Legacy-NDJSON-Dateien auf dem Host, falls solche Altbestaende vor dem Fix bereits vorhanden waren

Siehe auch: [OPEN_ITEMS.md](OPEN_ITEMS.md)
