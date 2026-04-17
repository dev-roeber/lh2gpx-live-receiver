# LH2GPX Receiver – Bedienung

## Login

1. Dashboard im Browser öffnen
2. vorgeschlagene Server-URL prüfen
3. Bearer-Token eingeben
4. anmelden

- erfolgreicher Login setzt einen signierten Session-Cookie
- ohne `ADMIN_USERNAME` / `ADMIN_PASSWORD` ist das Dashboard nur lokal erreichbar

## Karte

- `/dashboard/map` zeigt die letzten Punkte auf der Live-Karte
- Zeitraum, Polling, Session und Auto-Follow sind direkt steuerbar

## Punkte, Requests, Sessions

- **Punkte**: einzelne GPS-Punkte mit Zeit, Koordinaten und Accuracy
- **Requests**: empfangene Uploads inkl. Status und Fehlerkategorie
- **Sessions**: zusammengehörige Upload-Serien mit Zeitraum und Punktanzahl

## Import

- unterstützt `json`, `gpx`, `kml`, `kmz`, `geojson`, `csv`, `zip`
- Dedupe erfolgt über `Zeitstempel + Latitude + Longitude`
- doppelte Punkte werden übersprungen

## Exporte

- Punktliste als `CSV`, `JSON` oder `NDJSON`
- Session- und Zeitraumfilter greifen auch auf die Exporte
