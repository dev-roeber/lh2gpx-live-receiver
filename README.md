# lh2gpx-live-receiver

Receiver- und Operator-Server fuer optionale Live-Location-Uploads aus `LocationHistory2GPX-iOS`.

Diese Arbeit hat bewusst nur dieses Receiver-Repo und den Serverbetrieb geaendert. App, Wrapper und lokale Standortdaten wurden absichtlich nicht angefasst.

## Kurzstatus

- FastAPI-Receiver fuer `POST /live-location`
- SQLite als Standard-Persistenz fuer Requests und einzelne GPS-Punkte
- optionales NDJSON-Audit fuer Rohpayloads
- Dashboard fuer Betrieb, Diagnose und Exporte
- lokale oder Basic-Auth-geschuetzte Operator-Oberflaeche
- Docker-Compose-Deployment mit Caddy als TLS-Reverse-Proxy

## Root cause des bisherigen HTTP-500

Der bisherige 500er war kein Client-Schemafehler, sondern ein Server-Storage-Problem:

- der Dienst lief als `appuser`
- der aktive Volume-/Dateipfad fuer `live-location.ndjson` war im Container nicht sauber vorbereitet
- der Storage-Code schrieb blind append-only in eine Datei
- dadurch schlugen echte Requests mit `FileNotFoundError` fehl
- die alten Tests deckten diesen Runtime-Pfad nicht ab

Der aktuelle Stand beseitigt das ueber:

- vorbereitete und beschreibbare Daten- und Log-Verzeichnisse
- SQLite als primaeren Storage
- `readyz` fuer echte Schreibbereitschaft
- 503 statt blindem 500 bei Storage-Problemen
- strukturierte Request- und Fehlerlogs mit `request_id`

## Input contract

Der Receiver bleibt rueckwaertskompatibel zum bestehenden iOS-Live-Upload-Contract:

- `source`
- `sessionID`
- `captureMode`
- `sentAt`
- `points[]`
- `points[].latitude`
- `points[].longitude`
- `points[].timestamp`
- `points[].horizontalAccuracyM`

Unbekannte additive Zusatzfelder werden weiter toleriert und im Rohpayload gespeichert.

## Wichtige Endpunkte

- `GET /health`
  - Prozess lebt und liefert Grundstatus
- `GET /readyz`
  - Storage ist schreibbereit
- `POST /live-location`
  - akzeptiert valide Uploads und speichert Requests plus Punkte
- `GET /api/stats`
  - Kennzahlen fuer Requests, Punkte, Sessions und Zeitraeume
- `GET /api/points`
  - Punkteliste, Filter und Export
- `GET /api/points/{id}`
  - Punktdetail
- `GET /api/requests`
  - Requestliste
- `GET /api/requests/{request_id}`
  - Requestdetail inkl. Rohpayload
- `GET /api/sessions`
  - Session-Uebersicht
- `GET /api/sessions/{session_id}`
  - Sessiondetail mit Bounding Box und Zeitspanne
- `GET /dashboard`
  - Operator-UI

## Operator-UI

Das Dashboard zeigt:

- Gesamtanzahl Requests
- Gesamtanzahl Punkte
- letzte erfolgreiche Annahme
- letzte Fehler
- Storage-Pfade und Schreibstatus
- Punkte pro Tag
- Punkte pro Session
- gefilterte Punkteliste mit:
  - Datum
  - lokale Uhrzeit
  - UTC-Zeit
  - lokaler Zeitstempel
  - Latitude
  - Longitude
  - Accuracy
  - Session-ID
  - Source
  - Capture-Mode
  - Request-ID
  - Empfangszeit
- Request- und Session-Detailseiten
- CSV-, JSON- und NDJSON-Export der Punkteliste

Wenn `ADMIN_USERNAME` und `ADMIN_PASSWORD` leer sind, ist das Dashboard absichtlich nur lokal nutzbar. Mit gesetzten Credentials ist HTTP Basic Auth aktiv.

## Konfiguration

Die versionierte `.env.example` bleibt absichtlich neutral. Dort stehen keine fest eingebauten Produkt- oder Testserverwerte.

Wichtige ENV-Variablen:

- `PUBLIC_HOSTNAME`
- `PUBLIC_BASE_URL`
- `LIVE_LOCATION_BEARER_TOKEN`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `DATA_DIR`
- `SQLITE_PATH`
- `RAW_PAYLOAD_NDJSON_PATH`
- `LEGACY_REQUEST_NDJSON_PATH`
- `ENABLE_RAW_PAYLOAD_NDJSON`
- `LOCAL_TIMEZONE`
- `REQUEST_BODY_MAX_BYTES`
- `RATE_LIMIT_REQUESTS_PER_MINUTE`

Hinweis:

- Screenshot-Testdaten sind nur lokal und nicht versioniert zu verwenden.
- Der Bearer-Token darf nie in Git, README, Logs oder API-Responses landen.
- Dieses Repo liefert keine verpflichtende Online-Vorgabe fuer spaetere Nutzer aus.

## Lokaler Start

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
./scripts/run-local.sh
```

## Docker Compose

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=200
```

Der Backend-Port bleibt lokal auf `127.0.0.1:8080`. Oeffentlich wird nur Caddy auf `80/443` exponiert.

## Smoke-Test

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
./scripts/smoke-test.sh
```

Der Smoke-Test prueft:

- `GET /health`
- `GET /readyz`
- `POST /live-location`
- lokal optional Dashboard- und Punktlisten-Zugriff

## Weiterfuehrende Doku

- [docs/API.md](docs/API.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/APPSTORE_PRIVACY_NOTES.md](docs/APPSTORE_PRIVACY_NOTES.md)
- [docs/DEPLOY_RUNBOOK.md](docs/DEPLOY_RUNBOOK.md)
