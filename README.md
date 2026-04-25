# lh2gpx-live-receiver

Receiver- und Operator-Server für optionale Live-Location-Uploads aus der `LocationHistory2GPX`-App (Haupt-App-Repo: `dev-roeber/iOS-App`).

## Rolle im 5-Repo-System

- optionaler Self-Hosted-Receiver für Live-Punkte aus der iOS-App
- nicht erforderlich für lokalen Import, lokale Analyse oder lokale Exporte; diese Produktpfade bleiben ohne Pflicht-Online-Infrastruktur möglich
- gedacht für nutzerseitig selbst konfigurierte Server statt für eine zentrale Pflicht-Cloud
- Testserver- und Testwerte aus anderen Repos dürfen nicht als Produktstandard für diesen Receiver-Pfad gelesen werden

## Kurzstatus

- FastAPI-Receiver für `POST /live-location`
- SQLite als primäre Persistenz für Requests und einzelne GPS-Punkte
- optionales NDJSON-Audit für Rohpayloads
- interaktive Echtzeit-Karte mit MapLibre GL JS, lokalem Browser-Mirror und serverseitiger Layer-Aufbereitung
- Live-Punkt-Log mit konfigurierbarem Polling und Zeitraumfilter
- iOS-inspiriertes Dark-Design-System (OLED-Schwarz, semantische Akzentfarben)
- vollständig responsive Oberfläche (Desktop / Tablet / Mobile)
- Docker-Compose-Deployment mit Caddy als TLS-Reverse-Proxy

## Aktueller Stand

- **Design-System (April 2026):** Vollständig auf iOS-inspiriertes Dark-Design umgestellt. OLED-Schwarz als Hintergrund, Mint `#30D158` als primärer Akzent, semantische Farben (Blau, Orange, Lila, Rot, Teal) für Status und Kategorien. Glasmorphismus-Header, Pill-Buttons, gerundete Karten.
- **Interaktive Karte:** `/dashboard/map` mit MapLibre GL JS, separatem Metapfad `/api/map-meta`, viewport-basierten Layern über `/api/map-data`, eigenem Timeline-Endpoint `/api/timeline`, leichtem `/api/timeline-preview`, lokalem IndexedDB-Mirror via Dexie, hybrider Live-Aktualisierung aus WebSocket-Hinweisen, Delta-Refresh und konfigurierbarem Polling, Timeline-Scrubbing, Echtzeit-Replay, 3D-Pitch, GeoJSON-Export, Browser-Standort und Server-Verarbeitungsstatus.
- **Responsive:** CSS-Grid-basiertes 3-View-System. Desktop: Filter-Panel | Karte | Live-Log. Tablet: 2-Spalten. Mobile: vollständig gestackt, Filter einklappbar. Kartensteuerung und Layer-Menü sind auf kleinen Displays als getrennte Dropdowns nutzbar.
- **Sichere Operator-UI:** Karten-Live-Log und Import-Status rendern server- bzw. ingestnahe Inhalte nicht mehr als ungefiltertes HTML.
- **Login:** Bearer-basierter Dashboard-Login mit signiertem Session-Cookie. Nach Login Redirect auf `/dashboard/map`.
- **Deutsche Oberfläche:** Alle Dashboard-Seiten vollständig auf Deutsch lokalisiert.
- **iOS-Vollbild:** Native `requestFullscreen()` nicht auf iOS verfügbar → CSS-Fallback (`position:fixed; 100vw/100dvh`) per ⛶-Button. Einmaliger "Zum Home-Bildschirm"-Banner mit Anleitung. Android nutzt denselben Vollbild-Layoutpfad jetzt auch im nativen Fullscreen.

## Root cause des bisherigen HTTP-500

Der bisherige 500er war kein Client-Schemafehler, sondern ein Server-Storage-Problem:

- der Dienst lief als `appuser`
- der aktive Volume-/Dateipfad für `live-location.ndjson` war im Container nicht sauber vorbereitet
- der Storage-Code schrieb blind append-only in eine Datei
- dadurch schlugen echte Requests mit `FileNotFoundError` fehl

Der aktuelle Stand beseitigt das über:

- vorbereitete und beschreibbare Daten- und Log-Verzeichnisse
- SQLite als primären Storage
- `readyz` für echte Schreibbereitschaft
- 503 statt blindem 500 bei Storage-Problemen
- strukturierte Request- und Fehlerlogs mit `request_id`

## Input contract

Der Receiver bleibt rückwärtskompatibel zum bestehenden iOS-Live-Upload-Contract:

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
- `GET /api/live-summary`
  - Kompakter Echtzeit-Status inkl. neuester Punkte für Monitoring-Tools.
- `GET /api/stats`
  - Kennzahlen für Requests, Punkte, Sessions und Zeiträume.
- `GET /api/points`
  - Punkteliste mit Filter und Export.
- `GET /api/map-data`
  - serverseitig vorbereitete Layer für Karte, Heatmap, Track, Speed, Stops, Daytracks und optional Snap.
- `GET /api/timeline`
  - leichte Timeline-Daten inkl. Marker und Metadaten.
- `GET /api/timeline-preview`
  - leichter Karten-Preview-Pfad für Timeline und Replay.
- `POST /api/import`
  - startet asynchronen Dateiimport für `json`, `gpx`, `kml`, `kmz`, `geojson`, `geo.json`, `csv`, `zip`.
- `GET /api/import/status/{task_id}`
  - Polling-Status für laufende Import-Tasks inkl. Phase, Dateimetadaten, Parser-/ZIP-Warnungen und Importmetriken.
- `GET /api/points/{id}`
  - Punktdetail.
- `GET /api/requests`
  - Requestliste.
- `GET /api/requests/{request_id}`
  - Requestdetail inkl. Rohpayload.
- `GET /api/sessions`
  - Session-Übersicht.
- `GET /api/sessions/{session_id}`
  - Sessiondetail mit Bounding Box und Zeitspanne.
- `GET /dashboard`
  - Operator-UI (Redirect auf `/dashboard/map` nach Login).
- `GET /dashboard/map`
  - Interaktive Echtzeit-Karte.

## Operator-UI

### Design-System

iOS-inspiriertes Dark-Theme:

- **Hintergrund:** OLED-Schwarz `#000000`, Karten `#1C1C1E` / `#2C2C2E` / `#3A3A3C`
- **Primär-Akzent:** Mint `#30D158`
- **Semantische Farben:** Blau `#0A84FF`, Orange `#FF9F0A`, Lila `#BF5AF2`, Rot `#FF453A`, Teal `#5AC8FA`
- **Typografie:** `-apple-system, SF Pro Text/Display`
- **Komponenten:** Glasmorphismus-Header (`backdrop-filter: blur(20px)`), Pill-Buttons, semantische Status-Chips, KPI-Tiles mit Tints, Border-Radius 20px Karten / 12px klein / 999px Chips

### Informationsarchitektur

Jede Seite hat:
- **Global Header:** Hostname | Receiver-Status | Auth | Uptime | letzter Ingest | Version
- **Alert Strip:** akuter Receiver-Zustand in Farbe (grün OK / gelb WARN / rot CRIT)
- **Seiteninhalt**
- **Quick Actions:** kompakte Schnellwege zu den wichtigsten Operator-Seiten
- **Context Footer:** Bind, Storage-Status, Admin-Modus, Timezone

### Karte (`/dashboard/map`)

Interaktive GPS-Echtzeit-Karte mit:

- **MapLibre GL JS** als Karten-Engine, nicht mehr Leaflet
- **serverseitigem Kartenmodell** über `GET /api/map-data` und **globalen Kartenmetadaten** über `GET /api/map-meta`
- **separatem Timeline-Modell** über `GET /api/timeline` und leichtem Vorschaupfad `GET /api/timeline-preview`
- **viewport-basierter Datenladung**: der Server liefert primär Daten für die aktuelle Ansicht; `Fallback-Punkte` greift nur, wenn noch kein Viewport verfügbar ist
- **ingest-naher Vorberechnung** für:
  - globale und Session-Rollups
  - Timeline-Day-Marker
  - tile-basierte Raumspalten (`z10`, `z14`) als zusätzlicher Spatial-Fast-Path neben dem SQLite-RTree
- **serverseitig vorbereiteten Layern** für Punkte, Heatmap, Polylinien, Genauigkeit, Geschwindigkeit, Stops, Daytracks und optionalen Straßen-Snap
- **hybridem Live-Pfad**: WebSocket `/ws/map` signalisiert neue Daten; Polling bleibt als konfigurierbarer Refresh- und Fallback-Pfad aktiv
- **Delta-/Noop-Refresh**: unveränderte Ansichten erhalten `304`/Noop; bei Änderungen werden Punkte und Logs inkrementell ergänzt, Polylinien/Geschwindigkeit teils append-fähig verarbeitet und kontextabhängige Layer gezielt ersetzt
- **lokalem IndexedDB-Mirror** via Dexie für bereits geladene Punktdaten
- **Timeline-Scrubbing** mit:
  - Play/Pause
  - Start/Zurück/Jetzt/Vor/Ende
  - Geschwindigkeiten
  - Schrittmodus
  - Quelle `Ansicht` oder `Filter`
  - Echtzeit-Replay
  - Auto-Follow
  - Aktivitätsleiste und Marker-Strip
- **3D-Pitch-Toggle** für die MapLibre-Karte
- **Live-Polling:** 2s / 3s / 5s (Standard) / 10s / 15s / 20s / 30s / 45s / 1min / 1.5min / 2min / 3min / 5min
- **Zeitraumfilter:** 2min bis 30 Tage oder gesamt, mit localStorage-Persistenz
- **Session- und Import-Filter:** exklusive Auswahl per Dropdown
- **Auto-Follow:** Karte folgt automatisch dem neuesten eingehenden Punkt, ohne den gewählten Nutzer-Zoom zu erzwingen
- **Fit-Bounds-Modus:** `Gesamt` über globale `map-meta`-Bounding-Box oder `Ansicht` über aktuell sichtbare Layerdaten
- **GeoJSON-Export** des aktuell geladenen Kartenmodells
- **Browser-Standort** und separater Schnellzugriff auf den neuesten Serverpunkt
- **Vollbild:** native API auf Desktop/Android; CSS-Fallback (`position:fixed; 100vw/100dvh`) auf iOS
- **Live-Punkt-Log:** scrollbare Echtzeit-Tabelle direkt unter der Karte; reagiert direkt auf Filter- und Log-Limit-Änderungen; auf Mobile: Spalten `Genauigkeit`, `Modus`, `Request ID` ausgeblendet
- **Download-Fortschrittsoverlay** mit:
  - serverseitigen Timing-Phasen
  - Download-/Render-Phasen
  - ETA
  - Retry im Fehlerzustand
  - kompaktem Sync-Pill für schnelle Noop-/Delta-Fälle
- **Server-Verarbeitungsanzeige:** oberhalb der Karte wird angezeigt, ob alle verfügbaren Serverdaten verarbeitet sind, wie viele Punkte noch fehlen und welche Restdauer für laufende Importjobs geschätzt wird
- **Tempo-Legende:** `0–100 km/h` in `5 km/h`-Stufen; darüber kontinuierliche Farbskala

### Responsive Layout

| Breakpoint | Layout |
|---|---|
| ≥1440px | 3-Spalten: Filter-Panel (sticky) \| Karte (600px) \| Live-Log |
| 768–1439px | 2-Spalten oben, Filter full-width; Karte 450px |
| <768px | 1-Spalte; Filter-Panel einklappbar; Karte 350–400px |
| <1024px | Sidebar wird zur Top-Navigation |

CSS-Grid, `min-width:0` auf allen Grid-Children, `box-sizing:border-box` durchgängig. `clamp()` für fließende Skalierung. MapLibre-Resize über `map.resize()`, Viewport-Refresh, mobile Media Queries und Overlay-Layoutlogik direkt am Kartencontainer.

### Startseite (`/dashboard`)

6 kompakte Status-Kacheln mit STATUS-Badge (OK / WARN / CRIT / INFO):
- **Receiver:** Health, Readiness, letzter Ingest, Erfolgsquote
- **Security:** Ingest-Auth, Admin-Zugriff, letzte Fehlerkategorie
- **Storage:** SQLite-Größe, Raw-Audit-Größe, Schreibbarkeit
- **System:** Uptime, Startzeit
- **Ingest-Volumen:** Requests / Punkte / Sessions gesamt, Fehler gesamt
- **Aktivität:** Requests / Punkte heute und 24h

Darunter: priorisierte Next-Actions, jüngste Requests-Tabelle, Top-Sessions, neueste GPS-Punkte.

### Navigation (task-orientiert)

- **Overview:** Overview · Receiver Health · Aktivität
- **Daten:** Requests · Sessions · Punkte · Exporte
- **Betrieb & Sicherheit:** Security · Storage · Konfiguration · System
- **Hilfe:** Troubleshooting · Open Items

### Weitere Operator-Seiten

- gefilterte Punkteliste (Datum, lokale Uhrzeit, UTC-Zeit, Lat/Lon, Accuracy, Session-ID, Source, Capture-Mode, Request-ID, Empfangszeit)
- separate Request-, Session- und Punkt-Detailseiten
- Request-Historie mit Fehlerkategorien
- Session-Übersicht mit Requestanzahl und Accuracy-Mittelwert
- Storage-Dateigrößen und letzte Schreibzeiten
- maskierte Konfigurations- und Auth-Übersicht
- Troubleshooting- und Open-Items-Doku direkt in der UI
- Systemseite mit Version, Laufzeit und Changelog-Ausschnitten
- CSV-, JSON- und NDJSON-Export der Punkteliste

**Sicherheitshinweis:** Der Zugriffsschutz für das Dashboard erfolgt über signierte Session-Cookies oder optional HTTP Basic Auth. Ingest-Endpunkte sind Bearer-Token-gesichert.

## Konfiguration

Die versionierte `.env.example` bleibt absichtlich neutral. Dort stehen keine fest eingebauten Produkt- oder Testserverwerte.

Wichtige ENV-Variablen:

- `PUBLIC_HOSTNAME` / `PUBLIC_BASE_URL`
- `LIVE_LOCATION_BEARER_TOKEN` (Pflicht für Ingest-Sicherheit)
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` (Dashboard-Login)
- `SESSION_SIGNING_SECRET` (optional dedizierter Signing-Key für Dashboard-Cookies)
- `LOCAL_TIMEZONE` (IANA-Validierung beim Start; Zeitstempel werden als UTC in DB gespeichert, wenn `UTC` gesetzt)
- `DATA_DIR` / `SQLITE_PATH`
- `ENABLE_RAW_PAYLOAD_NDJSON`
- `LOG_LEVEL` (Standard: INFO)
- `POINTS_PAGE_SIZE_MAX` (Standard: 2000)

Hinweise:

- Screenshot-Testdaten sind nur lokal und nicht versioniert zu verwenden.
- Der Bearer-Token darf nie in Git, README, Logs oder API-Responses landen.
- Dieses Repo liefert keine verpflichtende Online-Vorgabe für spätere Nutzer aus.
- `ENABLE_RAW_PAYLOAD_NDJSON=true` aktiviert den optionalen Rohpayload-Export.
- Neue Rohpayload-Dateien werden mit `0600` angelegt; bestehende Dateien werden nicht automatisch nachträglich angepasst.
- `LOCAL_TIMEZONE=UTC` bedeutet, dass Zeitstempel als UTC gespeichert werden — der Zeitraumfilter auf der Karte arbeitet daher korrekt mit UTC-Werten.

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

Der Smoke-Test prüft:

- `GET /health`
- `GET /readyz`
- `POST /live-location`
- lokal optional Dashboard- und Punktlisten-Zugriff

## Weiterführende Doku

- [docs/API.md](docs/API.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/APPSTORE_PRIVACY_NOTES.md](docs/APPSTORE_PRIVACY_NOTES.md)
- [docs/DEPLOY_RUNBOOK.md](docs/DEPLOY_RUNBOOK.md)
- [docs/OPEN_ITEMS.md](docs/OPEN_ITEMS.md)
