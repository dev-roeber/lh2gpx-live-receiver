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

- dieser Fehlerpfad ist durch SQLite plus vorbereitete Schreibpfade abgesichert
- ein echter `500` sollte jetzt nur noch bei unerwarteten Fehlern auftreten

## Dashboard nicht erreichbar

Ohne Admin-Credentials:

- Dashboard ist absichtlich nur lokal erreichbar

Mit Admin-Credentials:

- Basic-Auth Header pruefen
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Punkte erscheinen nicht in der Liste

Pruefen:

- `readyz`
- `/api/points`
- `receiver.sqlite3` existiert
- Requestdetail unter `/api/requests/{request_id}`

## Export leer

Pruefen:

- aktive Filter im Dashboard oder Query-String
- ob Punkte ueberhaupt in SQLite gespeichert wurden
