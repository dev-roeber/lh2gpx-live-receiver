# LH2GPX Receiver – Bedienung

## Login

1. Dashboard im Browser öffnen
2. vorgeschlagene Server-URL prüfen
3. Bearer-Token eingeben
4. anmelden

- erfolgreicher Login setzt einen signierten Session-Cookie
- ohne `ADMIN_USERNAME` / `ADMIN_PASSWORD` ist das Dashboard nur lokal erreichbar

## Karte

- `/dashboard/map` lädt globale Kartenmetadaten und ein serverseitig vorbereitetes Kartenmodell
- steuerbar sind:
  - Zeitraum
  - Polling
  - Fit-Bounds-Modus `Gesamt` oder `Ansicht`
  - Fallback-Punkte, falls noch kein Karten-Viewport verfügbar ist
  - Session- oder Import-Filter
  - Auto-Follow oder Fit-Bounds
  - Layer für Punkte, Heatmap, Linien, Genauigkeit, Labels, Tempo, Stops, Tages-Tracks und Snap
- die Kartensteuerung liegt im Dropdown `☰ Karte`
- im Kartenmenü gibt es einen Browser-Standort-Button für den aktuellen Gerätestandort
- im Kartenmenü gibt es zusätzlich `3D`, `Vollbild`, `Legende`, `Refresh` und den Schnellzugriff auf den neuesten Serverpunkt
- `Auto-Follow` behält den aktuellen Zoom
- der normale Linien-Layer ist straßennäher, weil serverseitig gesnappte Geometrie bevorzugt wird
- die Karte lädt viewport-basiert; bei Bewegung und Zoom wird die aktuelle Ansicht neu angefordert
- Live-Updates laufen hybrid über WebSocket-Hinweise, Delta-Refresh und das eingestellte Polling
- ein Timeline-Regler kann die aktuell geladenen Punkte zeitlich abspielen oder filtern
- GeoJSON exportiert den aktuell geladenen Kartenstand
- oberhalb der Karte zeigt eine Server-Verarbeitungsanzeige, ob laufende Importdaten schon vollständig verarbeitet sind, wie viele Punkte noch fehlen und welche ETA aktuell geschätzt wird
- während des Downloads zeigt ein Overlay echte geladene Bytes und, falls bekannt, den Prozentfortschritt

## Punkte, Requests, Sessions

- **Punkte**: einzelne GPS-Punkte mit Zeit, Koordinaten und Accuracy
- **Requests**: empfangene Uploads inkl. Status und Fehlerkategorie
- **Sessions**: zusammengehörige Upload-Serien mit Zeitraum und Punktanzahl

## Import

- unterstützt `json`, `gpx`, `kml`, `kmz`, `geojson`, `geo.json`, `csv`, `zip`
- Dedupe erfolgt über `Zeitstempel + Latitude + Longitude`
- doppelte Punkte werden übersprungen
- auf iPhone/Mobile Safari ist der Datei-Picker speziell gehärtet
- nach dem Upload zeigt die Seite den Serverfortschritt live an:
  - Phase des Imports
  - Dateiname, Dateigröße und erkanntes Format
  - Rohpunkte, neu importierte Punkte und übersprungene Punkte
  - Dedupe innerhalb der Datei und bereits vorhandene Punkte in der Datenbank
  - bei ZIP auch Gesamtzahl, genutzte und fehlgeschlagene Einträge
  - Parse-, Insert- und Gesamtdauer
  - Warnungen oder Fehlerkategorie direkt aus dem Serverstatus

## Exporte

- Punktliste als `CSV`, `JSON` oder `NDJSON`
- Session- und Zeitraumfilter greifen auch auf die Exporte
