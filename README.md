# lh2gpx-live-receiver

Receiver- und Operator-Server für optionale Live-Location-Uploads aus der `LocationHistory2GPX`-App (Haupt-App-Repo: `dev-roeber/iOS-App`).

Diese Arbeit hat bewusst nur dieses Receiver-Repo und den Serverbetrieb geändert. App, Wrapper und lokale Standortdaten wurden absichtlich nicht angefasst.

## Rolle im 5-Repo-System

- optionaler Self-Hosted-Receiver für Live-Punkte aus der iOS-App
- nicht erforderlich für lokalen Import, lokale Analyse oder lokale Exporte; diese Produktpfade bleiben ohne Pflicht-Online-Infrastruktur moeglich
- gedacht für nutzerseitig selbst konfigurierte Server statt für eine zentrale Pflicht-Cloud
- Testserver/Testwerte aus anderen Repos dürfen nicht als Produktstandard für diesen Receiver-Pfad gelesen werden

## Kurzstatus

- FastAPI-Receiver für `POST /live-location`
- SQLite als Standard-Persistenz für Requests und einzelne GPS-Punkte
- optionales NDJSON-Audit für Rohpayloads
- Dashboard für Betrieb, Diagnose und Exporte
- verbesserte Loopback-Erkennung für Docker-Bridge-Umgebungen
- Docker-Compose-Deployment mit Caddy als TLS-Reverse-Proxy

## Aktueller Stand

- **Integration abgeschlossen (April 2026):** Die lokal entwickelten Verbesserungen (Features, Stabilität, Refactoring) wurden vollständig in den `main`-Branch integriert.
- **Vereinfachte Sicherheit:** Die integrierte HTTP Basic Auth via `ADMIN_USERNAME`/`PASSWORD` wurde aus der Standard-`compose.yaml` entfernt, um das Deployment zu vereinfachen. Das Dashboard ist nun standardmäßig im lokalen Netz/über den Proxy zugänglich.
- **Feature-Zuwachs:** Neuer High-Performance API-Endpunkt `/api/live-summary` für Echtzeit-Dashboards integriert.
- **Robustheit:** Der Server stürzt nicht mehr ab, wenn die Datenbank fehlt oder nicht schreibbar ist; er liefert stattdessen einen Fallback-Status (Readiness-Check).

## Root cause des bisherigen HTTP-500

Der bisherige 500er war kein Client-Schemafehler, sondern ein Server-Storage-Problem:

- der Dienst lief als `appuser`
- der aktive Volume-/Dateipfad für `live-location.ndjson` war im Container nicht sauber vorbereitet
- der Storage-Code schrieb blind append-only in eine Datei
- dadurch schlugen echte Requests mit `FileNotFoundError` fehl
- dieser konkrete Runtime-Pfad ist im aktuellen Stand behoben; neue `raw-payloads.ndjson`-Dateien werden mit `0600` angelegt
- vorhandene `raw-payloads.ndjson`- oder Legacy-`live-location.ndjson`-Dateien in bestehenden Deployments werden dadurch nicht automatisch umgestellt und müssen operativ geprueft werden
- die alten Tests deckten diesen Runtime-Pfad nicht ab

Der aktuelle Stand beseitigt das über:

- vorbereitete und beschreibbare Daten- und Log-Verzeichnisse
- SQLite als primaeren Storage
- `readyz` für echte Schreibbereitschaft
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

- `GET /health` / `GET /readyz`
  - Prozess-Check und Schreibbereitschaft (Storage-Check).
- `POST /live-location`
  - Akzeptiert Uploads (iOS-kompatibel) und speichert Requests + Punkte.
- `GET /api/live-summary` (NEU)
  - Kompakter Echtzeit-Status inkl. neuester Punkte für Monitoring-Tools.
- `GET /api/stats`
  - Kennzahlen für Requests, Punkte, Sessions und Zeitraeume
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

Die Admin-Oberfläche (v0.5) ist als receiver-first Operator-Workspace mit moderner Informationsarchitektur aufgebaut.

### Informationsarchitektur

Jede Seite hat:
- **Global Header**: Hostname | Receiver-Status | Auth | Uptime | letzter Ingest | Version
- **Alert Strip**: akuter Receiver-Zustand in Farbe (gruen OK / gelb WARN / rot CRIT)
- **Seiteninhalt**
- **Quick Actions**: kompakte Schnellwege zu den wichtigsten Operator-Seiten
- **Context Footer**: Bind, Storage-Status, Admin-Modus, Timezone

### Startseite (Overview / Dashboard)

6 kompakte Status-Kacheln mit STATUS-Badge (OK / WARN / CRIT / INFO):
- **Receiver**: Health, Readiness, letzter Ingest, Erfolgsquote
- **Security**: Ingest-Auth, Admin-Zugriff, letzte Fehlerkategorie
- **Storage**: SQLite-Größe, Raw-Audit-Größe, Schreibbarkeit
- **System**: Uptime, Startzeit
- **Ingest-Volumen**: Requests/Punkte/Sessions gesamt, Fehler gesamt
- **Aktivität**: Requests/Punkte heute und 24h

Darunter: priorisierte Next-Actions, jüngste Requests-Tabelle, Top-Sessions, neueste GPS-Punkte.

### Navigation (task-orientiert)

- **Overview**: Overview · Receiver Health · Aktivität
- **Daten**: Requests · Sessions · Punkte · Exporte
- **Betrieb & Sicherheit**: Security · Storage · Konfiguration · System
- **Hilfe**: Troubleshooting · Open Items

### Compact / Full Mode

- schmale Terminals und Portrait-Geraete (unter 600px): Kacheln einspaltg, Tabellen vereinfacht
- Standard-Desktopbreiten: volle 3-spaltige Kacheln, 2-spaltige Content-Grids
- unter 900px: Sidebar wird zur Top-Navigation, kein sticky Scrollbereich

Weitere Operator-Seiten zeigen unter anderem:

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
- separate Request-, Session- und Punkt-Detailseiten
- Request-Historie mit Fehlerkategorien
- Session-Uebersicht mit Requestanzahl und Accuracy-Mittelwert
- Storage-Dateigrößen und letzte Schreibzeiten
- maskierte Konfigurations- und Auth-Uebersicht
- Troubleshooting- und Open-Items-Doku direkt in der UI
- Systemseite mit Version, Laufzeit und Changelog-Ausschnitten
- CSV-, JSON- und NDJSON-Export der Punkteliste

**Hinweis zur Sicherheit:** Der Zugriffsschutz für das Dashboard erfolgt aktuell primär über die Netzwerk-Ebene (Localhost-Binding) oder den vorgeschalteten Reverse-Proxy (Caddy). Eine app-interne Authentifizierung ist im aktuellen Stand für maximale Portabilität deaktiviert.

## Konfiguration

Die versionierte `.env.example` bleibt absichtlich neutral. Dort stehen keine fest eingebauten Produkt- oder Testserverwerte.

Wichtige ENV-Variablen:

- `PUBLIC_HOSTNAME` / `PUBLIC_BASE_URL`
- `LIVE_LOCATION_BEARER_TOKEN` (Pflicht für Ingest-Sicherheit)
- `LOCAL_TIMEZONE` (Jetzt mit IANA-Validierung beim Start)
- `DATA_DIR` / `SQLITE_PATH`
- `ENABLE_RAW_PAYLOAD_NDJSON`
- `LOG_LEVEL` (Standard: INFO)

Hinweis:

- Screenshot-Testdaten sind nur lokal und nicht versioniert zu verwenden.
- Der Bearer-Token darf nie in Git, README, Logs oder API-Responses landen.
- Dieses Repo liefert keine verpflichtende Online-Vorgabe für spätere Nutzer aus.
- `ENABLE_RAW_PAYLOAD_NDJSON=true` aktiviert den optionalen Rohpayload-Export; bei `false` bleibt er aus.
- Neue Rohpayload-Dateien werden mit `0600` angelegt, bestehende Dateien werden nicht automatisch nachtraeglich angepasst.

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

Der Backend-Port bleibt lokal auf `127.0.0.1:8080`. Öffentlich wird nur Caddy auf `80/443` exponiert.

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

## Real verifizierter Stand

Im finalen Receiver-Lauf wurden auf dem Server unter anderem erfolgreich geprueft:

- `docker compose pull`
- `docker compose build`
- `docker compose up -d`
- `docker compose ps`
- `./scripts/smoke-test.sh`

Relevant bestaetigt wurden dabei:

- Receiver laeuft
- Caddy laeuft
- `health` liefert `200`
- `readyz` liefert `200`
- Live-Ingest liefert `202`
- Dashboard und Punkteliste sind erreichbar
- reale Punkte mit Koordinaten und Zeitstempeln werden gespeichert und angezeigt

Beobachteter Betriebsbefund:

- parallel laufende Uploads kamen erfolgreich am Receiver an
- dieser Befund wird hier nur als beobachteter Server-/Betriebszustand festgehalten
- daraus wurden in diesem Lauf bewusst keine App- oder Wrapper-Schluesse abgeleitet

Die bewussten Folgearbeiten stehen gesammelt in [docs/OPEN_ITEMS.md](docs/OPEN_ITEMS.md).

## Weiterfuehrende Doku

- [docs/API.md](docs/API.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/APPSTORE_PRIVACY_NOTES.md](docs/APPSTORE_PRIVACY_NOTES.md)
- [docs/DEPLOY_RUNBOOK.md](docs/DEPLOY_RUNBOOK.md)
- [docs/OPEN_ITEMS.md](docs/OPEN_ITEMS.md)
