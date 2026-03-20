# Deploy Runbook

Dieses Repo ist fuer den aktuell verifizierten Hostzustand auf **Docker Compose mit direktem Port** ausgelegt.

## Preflight-Basis fuer diese Entscheidung

Verifiziert auf diesem Server:
- `docker`: vorhanden
- `docker compose`: vorhanden
- `python3`: vorhanden
- `systemd`: vorhanden
- `uvicorn`: nicht global installiert
- `nginx`: nicht installiert
- `caddy`: nicht installiert
- verifizierte laufende Compose-Projekte: keine
- verifizierte Reverse-Proxy-Konfiguration fuer diesen Dienst: keine
- verifizierte externe Adresse: Server-IP `178.104.51.78`

Konsequenz:
- nur eine Deploy-Variante in diesem Repo
- direkte Port-Freigabe auf `8080/tcp`
- ohne TLS nur temporaerer HTTP-Zustand
- der Container laeuft hier bewusst als UID/GID `1000`, damit der bind-mountete Ordner `./data` auf diesem Host direkt beschreibbar bleibt

## Erstes Deploy

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
cp .env.example .env
docker compose build
docker compose up -d
sudo -n ufw allow 8080/tcp
```

## Laufende Verwaltung

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
docker compose ps
docker compose logs --tail=100
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

## Datenspeicher

- Standard-Datei: `./data/live-location.ndjson`
- pro Request genau eine neue Zeile
- append-only

## Naechster kleine Ausbau-Schritt

Wenn dieser Minimalreceiver stabil laeuft, ist der naechste sinnvolle Schritt:
- HTTPS sauber davorhaengen, idealerweise per Domain + Reverse-Proxy

Nicht Teil dieses Schritts:
- Datenbank
- UI/Dashboard
- Multi-User
- Kartenansicht
- Historienbrowser
