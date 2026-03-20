# lh2gpx-live-receiver

Minimaler, eigenstaendiger Live-Location-Receiver fuer `LocationHistory2GPX-iOS`.

Dieser erste Serverschritt ist absichtlich klein:
- eine FastAPI-App
- `GET /health`
- `POST /live-location`
- optionaler Bearer-Token ueber ENV
- append-only Speicherung als NDJSON
- HTTPS-Termination ueber Caddy
- keine Datenbank, kein Dashboard, kein Multi-User-Backend

## Repo-Truth / Input-Contract

Der Request-Body orientiert sich an der aktuell vorhandenen iOS-Client-Implementierung in `LocationHistory2GPX-iOS`:
- `source`
- `sessionID`
- `captureMode`
- `sentAt`
- `points[]` mit `latitude`, `longitude`, `timestamp`, `horizontalAccuracyM`

Unbekannte Zusatzfelder werden bewusst toleriert und mitgespeichert, solange die Grundstruktur gueltig bleibt.

## API

### `GET /health`

Antwortet mit kleinem Service-Status:

```json
{
  "status": "ok",
  "time": "2026-03-20T12:00:00+00:00",
  "service": "lh2gpx-live-receiver",
  "authRequired": false,
  "dataFile": "/app/data/live-location.ndjson",
  "dataFileExists": true
}
```

### `POST /live-location`

- akzeptiert JSON
- validiert Grundstruktur defensiv
- schreibt pro Request genau eine NDJSON-Zeile nach `DATA_DIR/live-location.ndjson`
- liefert bei Erfolg `202 Accepted`

Beispielantwort:

```json
{
  "status": "accepted",
  "pointsAccepted": 1,
  "dataFile": "/app/data/live-location.ndjson"
}
```

## Konfiguration

Nur ueber ENV:

- `PORT`
- `BIND_HOST`
- `LIVE_LOCATION_BEARER_TOKEN`
- `DATA_DIR`
- `LOG_LEVEL`

Siehe [.env.example](.env.example).

## Lokaler Start ohne Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
./scripts/run-local.sh
```

## Deploy-Entscheidung fuer diesen Host

Fuer diesen Server ist genau **Docker Compose mit Caddy als kleinem TLS-Reverse-Proxy** umgesetzt.

Begruendung anhand des Preflight-Ist-Zustands:
- `docker` und `docker compose` sind vorhanden und der Docker-Daemon laeuft
- globales `uvicorn` ist nicht vorhanden
- kein Host-`nginx` und kein Host-`caddy` sind installiert
- es existiert aktuell kein vorhandener Compose-Stack fuer diesen Dienst
- keine verifizierte eigene Domain ist vorhanden, aber `sslip.io` liefert fuer die Server-IP einen verifizierbaren Hostnamen

Der Receiver wird deshalb im bestehenden Compose-Stack betrieben:
- FastAPI nur noch lokal auf `127.0.0.1:8080`
- Caddy oeffentlich auf `80/443`
- TLS-Endpunkt fuer die App: `https://178-104-51-78.sslip.io/live-location`

## Netzwerkstatus dieses Setups

Dieses Setup ist jetzt **klein-produktionsnah fuer App-Tests mit gueltigem HTTPS-Endpunkt**:
- oeffentliche Endpunkte: `80/tcp` und `443/tcp`
- App-Ziel: `https://178-104-51-78.sslip.io/live-location`
- lokaler Backend-Port: `127.0.0.1:8080`
- `8080` ist kein oeffentlicher App-Endpunkt mehr

## Smoke-Test

Ein kleines Skript liegt unter [scripts/smoke-test.sh](scripts/smoke-test.sh).
Wenn im Repo eine `.env` liegt, nutzt das Skript diese automatisch.

Direkte Beispiele lokal:

```bash
curl http://127.0.0.1:8080/health
```

```bash
curl -X POST http://127.0.0.1:8080/live-location \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "LocationHistory2GPX-iOS",
    "sessionID": "123e4567-e89b-12d3-a456-426614174000",
    "captureMode": "foregroundWhileInUse",
    "sentAt": "2026-03-20T12:00:00Z",
    "points": [
      {
        "latitude": 52.52,
        "longitude": 13.405,
        "timestamp": "2026-03-20T11:59:59Z",
        "horizontalAccuracyM": 6.5
      }
    ]
  }'
```

Wenn `LIVE_LOCATION_BEARER_TOKEN` gesetzt ist:

```bash
curl -X POST http://127.0.0.1:8080/live-location \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${LIVE_LOCATION_BEARER_TOKEN}" \
  -d @sample-payload.json
```

Oeffentlicher HTTPS-Check:

```bash
curl https://178-104-51-78.sslip.io/health
```

## Tests

```bash
source .venv/bin/activate
pytest
```

## Deploy-Runbook

Das konkrete Deploy-Runbook liegt in [docs/DEPLOY_RUNBOOK.md](docs/DEPLOY_RUNBOOK.md).
