# LH2GPX Receiver – Bedienung

## Login

1. Dashboard im Browser öffnen
2. vorgeschlagene Server-URL prüfen
3. Bearer-Token eingeben
4. anmelden

- erfolgreicher Login setzt einen signierten Session-Cookie
- ohne `ADMIN_USERNAME` / `ADMIN_PASSWORD` ist das Dashboard nur lokal erreichbar

## Karte

- `/dashboard/map` lädt ein serverseitig vorbereitetes Kartenmodell
- steuerbar sind:
  - Zeitraum
  - Polling
  - Maximalzahl geladener Punkte
  - Session- oder Import-Filter
  - Auto-Follow oder Fit-Bounds
  - Layer für Punkte, Heatmap, Linien, Genauigkeit, Labels, Tempo, Stops, Tages-Tracks und Snap
- die Kartensteuerung liegt im Dropdown `☰ Karte`
- `Auto-Follow` behält den aktuellen Zoom
- der normale Linien-Layer ist straßennäher, weil serverseitig gesnappte Geometrie bevorzugt wird
- GeoJSON exportiert den aktuell geladenen Kartenstand

## Punkte, Requests, Sessions

- **Punkte**: einzelne GPS-Punkte mit Zeit, Koordinaten und Accuracy
- **Requests**: empfangene Uploads inkl. Status und Fehlerkategorie
- **Sessions**: zusammengehörige Upload-Serien mit Zeitraum und Punktanzahl

## Import

- unterstützt `json`, `gpx`, `kml`, `kmz`, `geojson`, `geo.json`, `csv`, `zip`
- Dedupe erfolgt über `Zeitstempel + Latitude + Longitude`
- doppelte Punkte werden übersprungen
- auf iPhone/Mobile Safari ist der Datei-Picker speziell gehärtet

## Exporte

- Punktliste als `CSV`, `JSON` oder `NDJSON`
- Session- und Zeitraumfilter greifen auch auf die Exporte
