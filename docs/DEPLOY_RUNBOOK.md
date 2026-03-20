# Deploy Runbook

Dieses Repo ist fuer den aktuell verifizierten Hostzustand auf **Docker Compose mit Caddy-TLS-Proxy** ausgelegt.

## Preflight-Basis fuer diese Entscheidung

Verifiziert auf diesem Server:
- `docker`: vorhanden
- `docker compose`: vorhanden
- `python3`: vorhanden
- `systemd`: vorhanden
- `uvicorn`: nicht global installiert
- Host-`nginx`: nicht installiert
- Host-`caddy`: nicht installiert
- verifizierte laufende Compose-Projekte: keine
- verifizierte Reverse-Proxy-Konfiguration fuer diesen Dienst vor diesem Schritt: keine
- verifizierte externe Adresse: Server-IP `178.104.51.78`
- verifizierbarer DNS-Hostname fuer diese IP: `178-104-51-78.sslip.io`

Konsequenz:
- nur eine Deploy-Variante in diesem Repo
- FastAPI bleibt intern auf `127.0.0.1:8080`
- Caddy exponiert `80/tcp` und `443/tcp`
- App-Endpunkt ist HTTPS auf `https://178-104-51-78.sslip.io`
- der Container laeuft hier bewusst als UID/GID `1000`, damit der bind-mountete Ordner `./data` auf diesem Host direkt beschreibbar bleibt

## Erstes Deploy

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
cp .env.example .env
docker compose build
docker compose up -d
sudo -n ufw allow 80/tcp
sudo -n ufw allow 443/tcp
sudo -n ufw delete allow 8080/tcp
```

## Laufende Verwaltung

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
docker compose ps
docker compose logs --tail=100
docker compose logs --tail=100 caddy
docker compose restart
docker compose down
```

## Update-Deploy

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
git pull --ff-only
docker compose build
docker compose up -d
```

## Lokale Smoke-Checks auf dem Server

Ohne Bearer-Token:

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
./scripts/smoke-test.sh
```

Mit Bearer-Token:

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
export LIVE_LOCATION_BEARER_TOKEN='replace-me'
./scripts/smoke-test.sh
```

Hinweis:
- wenn im Repo eine `.env` liegt, laedt `./scripts/smoke-test.sh` diese automatisch

## Oeffentliche HTTPS-Smoke-Checks

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
BASE_URL="https://178-104-51-78.sslip.io" ./scripts/smoke-test.sh
```

## Datenspeicher

- Standard-Datei: `./data/live-location.ndjson`
- pro Request genau eine neue Zeile
- append-only

## Naechster kleine Ausbau-Schritt

Wenn dieser Minimalreceiver stabil laeuft, ist der naechste sinnvolle Schritt:
- echte eigene Domain statt `sslip.io`
- danach optional App-Default-Endpunkt von `http://...` auf den HTTPS-Endpunkt umstellen

Nicht Teil dieses Schritts:
- Datenbank
- UI/Dashboard
- Multi-User
- Kartenansicht
- Historienbrowser
