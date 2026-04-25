# Troubleshooting

## `POST /live-location` liefert `401`

Ursache:

- Bearer-Token fehlt oder stimmt nicht

Pruefen:

- `LIVE_LOCATION_BEARER_TOKEN` in der lokalen `.env`
- `Authorization: Bearer ...` Header im Client

## `POST /live-location` liefert `422`

Ursache:

- Payload stimmt nicht zum Receiver-Contract

Pruefen:

- `source`
- `sessionID`
- `captureMode`
- `sentAt`
- `points[].latitude`
- `points[].longitude`
- `points[].timestamp`
- `points[].horizontalAccuracyM`

## `readyz` liefert `503`

Ursache:

- Datenpfad nicht schreibbar
- SQLite-Datei nicht anlegbar
- Rechteproblem auf dem bind-mounteten Verzeichnis

Pruefen:

- `docker compose logs --tail=200`
- `ls -ld data logs`
- `docker exec lh2gpx-live-receiver sh -lc 'id && ls -ld /app/data /app/logs'`

## `500` bei echten Uploads

Historisch gefundene Hauptursache:

- der alte NDJSON-Pfad war im Container nicht sauber vorbereitet und schlug mit `FileNotFoundError` fehl

Aktueller Stand:

- dieser konkrete Fehlerpfad ist im Repo behoben; neue `raw-payloads.ndjson`-Dateien werden jetzt mit `0600` angelegt
- bereits vorhandene Raw-Payload- oder Legacy-`live-location.ndjson`-Dateien werden dadurch nicht automatisch umgestellt
- ein echter `500` sollte jetzt nur noch bei unerwarteten Fehlern oder operativen Altbestaenden auftreten

Pruefen bei Altbestand:

- existiert `RAW_PAYLOAD_NDJSON_PATH` bereits vor dem Fix, ggf. Dateirechte und Besitzer auf dem Host kontrollieren
- bei Legacy-Dateien die Migrations-/Importspur separat bewerten, statt einen Repo-Fix anzunehmen

## Dashboard nicht erreichbar

Ohne Admin-Credentials:

- Dashboard ist absichtlich nur lokal erreichbar

Mit Admin-Credentials:

- Basic-Auth Header prüfen
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- falls einzelne Menüpunkte nicht laden: dieselbe Admin-Auth muss auch für `/dashboard/*` Unterseiten mitgesendet werden

## Punkte erscheinen nicht in der Liste

Pruefen:

- `readyz`
- `/api/points`
- `receiver.sqlite3` existiert
- Requestdetail unter `/api/requests/{request_id}`
- HTML-Punktliste unter `/dashboard/points`

## Karte lädt langsam oder unvollständig

Pruefen:

- `/readyz`
- `/dashboard/map`
- `/api/map-meta`
- `/api/map-data`
- `/api/timeline`
- `/api/timeline-preview`
- `/ws/map`
- ob `include_snap=true` aktiv ist; dieser Layer ist bewusst der teuerste Pfad
- Container-Logs auf Laufzeiten von `/api/map-data`
- Browser-Konsole auf MapLibre-/WebSocket-/IndexedDB-Fehler

Hinweise:

- ohne Snap ist die serverseitige Kartenpipeline deutlich schneller
- mit Snap sind mehrere Sekunden Laufzeit möglich, weil der Server OSRM-Matching anfragt und cacht
- Timeline/Replay nutzen bewusst leichtere Endpunkte; bei zähem Scrubbing zuerst `/api/timeline-preview` und die Browser-Konsole prüfen
- die Karte arbeitet hybrid aus WebSocket-Hinweisen, Polling und Delta-Refresh; ein WebSocket-Problem blockiert die Karte daher nicht komplett, kann aber Live-Reaktivität verschlechtern

## Export leer

Pruefen:

- aktive Filter im Dashboard oder Query-String
- ob Punkte überhaupt in SQLite gespeichert wurden
- für gefilterte HTML-Exporte zuerst `/dashboard/points` prüfen und die gesetzten Filter kontrollieren

## Was diese Fehlerhilfe bewusst nicht abdeckt

Dieses Troubleshooting beschreibt den aktuellen Receiver-Kern. Noch nicht Teil dieses Laufs:

- Session-Login-/Admin-Auth-Fehlerbilder einer späteren eigenständigen Admin-Schicht
- Cron-/Retention-/Backup-Job-Fehlerbilder
- App- oder Wrapper-seitige Fehlersuche außerhalb dieses Repos

Die offen verschobenen Punkte stehen gesammelt in [OPEN_ITEMS.md](OPEN_ITEMS.md).

## Aktueller Abschlussstand

- der aktuelle Receiver-Kern ist verifiziert und nach `main` gemergt
- ein zusätzlicher Post-Merge-Check auf `main` zeigte keinen unerwarteten Rückschritt
- neue Probleme aus diesem Abschlusscheck müssen derzeit nicht nachgezogen werden
