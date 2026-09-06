# Deploy Runbook

Dieses Runbook beschreibt nur den Receiver-/Serverbetrieb. App, Wrapper und lokale Standortdateien sind bewusst nicht Teil dieses Schritts.

## Betriebsmodi

Der aktuelle Produktionsbetrieb läuft als User-systemd-Dienst mit der
projektinternen `.venv`:

- Unit: `lh2gpx-live-receiver.service`
- Arbeitsverzeichnis: `/home/sebastian/services/lh2gpx-live-receiver`
- Bind: `127.0.0.1:8082`
- öffentlicher Einstieg: zentraler Dashboard-Proxy unter
  `https://devroeber.tail71a8bc.ts.net/receiver/dashboard`

Docker Compose ist nur ein optionaler Standalone-Betriebsmodus. Dort gilt der
in `compose.yaml` konfigurierte lokale Port (derzeit `127.0.0.1:8080`); dieser
Modus ist nicht die laufende Produktionsinstanz.

Für den jeweiligen Modus werden eine lokale `.env` und ausschließlich lokal
gespeicherte, nicht versionierte Werte benötigt.

## Voraussetzungen

- für den Produktionsbetrieb: User-systemd und die projektinterne `.venv`
- für den optionalen Standalone-Modus: Docker und `docker compose`

## Erstes Setup: optionaler Compose-Standalone-Modus

```bash
cd /home/sebastian/services/lh2gpx-live-receiver
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

## Produktionsbetrieb per User-systemd

```bash
cd /home/sebastian/services/lh2gpx-live-receiver
systemctl --user daemon-reload
systemctl --user enable --now lh2gpx-live-receiver.service
systemctl --user status lh2gpx-live-receiver.service
curl http://127.0.0.1:8082/health
curl http://127.0.0.1:8082/readyz
```

## Post-merge verification im optionalen Compose-Modus

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

## Update-Deploy im optionalen Compose-Modus

```bash
cd /home/sebastian/services/lh2gpx-live-receiver
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

- Der Receiver übernimmt die zentrale Dashboard-Session aus `DASHBOARD_SESSIONS_DB`.
- Nicht angemeldete Browser werden zur zentralen `DASHBOARD_LOGIN_URL` weitergeleitet.
- Der Cookie-Name ist `ytdl_session`; Cookies sind nicht port-spezifisch und funktionieren daher auch über Tailscale Funnel.

## Sichere Defaults

- keine versionierte produktive Hostvorgabe
- kein versionierter Bearer-Token
- keine Klartext-Anzeige von Secrets in API oder UI
- weitergehende Produktionshärtung wie Retention-Automatisierung oder Job-Scheduling ist bewusst nicht Teil dieses Laufs

## Rollback

```bash
cd /home/sebastian/services/lh2gpx-live-receiver
docker compose down
git checkout <bekannter-commit>
docker compose build
docker compose up -d
```

Wenn die Datenbasis erhalten bleiben soll, `./data` nicht löschen.

## Bewusst verschobene Folgearbeit

Vor einem breiteren produktiven Betrieb weiterhin offen:

- formalisierte Backup-/Restore-Automatisierung
- automatische Retention-/Export-Jobs
- finaler App-/Wrapper-Abgleich außerhalb dieses Repos
- Härtung bereits existierender Raw-Payload- oder Legacy-NDJSON-Dateien auf dem Host, falls solche Altbestaende vor dem Fix bereits vorhanden waren

Siehe auch: [OPEN_ITEMS.md](OPEN_ITEMS.md)
