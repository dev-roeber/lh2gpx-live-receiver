# Webseite – Bedienung

## Einstieg

- `/login` für Bearer-basierten Dashboard-Login
- `/dashboard` leitet auf die Kartenansicht weiter

## Hauptbereiche

- `Übersicht`: Receiver-Zustand und Kennzahlen
- `Karte`: Live-Karte mit serverseitig vorbereiteten Layern, Kartensteuerungs-Dropdown, Zeitraum, Session-/Import-Filter und GeoJSON-Export
- `Punkte`: punktgenaue Detailansicht
- `Requests`: Upload-Historie
- `Sessions`: Session-Übersicht und Löschpfad
- `Import`: Dateiimport mit Task-Status
- `Storage`, `Config`, `Security`, `System`: Betriebs- und Diagnoseansicht

## Karte

- die Karte lädt ihre Layer über `/api/map-data`
- `Max. Punkte`, Zeitfenster und Layer-Schalter wirken direkt auf das geladene Kartenmodell
- `Session Länge` und Kartenstatistik basieren auf den tatsächlich geladenen Track-Daten
- das Live-Log wird bei Filterwechseln sauber neu aufgebaut
- das Live-Log rendert ingestnahe Texte nur noch als Text und nicht als HTML
- die Kartensteuerung sitzt als eigenes Dropdown `☰ Karte` oberhalb des Layer-Menüs
- die Kartensteuerung enthält zusätzlich einen Browser-Standort-Button
- `Auto-Center` behält den aktuellen Nutzer-Zoom bei
- normale `Linien` folgen Straßen deutlich näher, weil der Polyline-Layer bevorzugt serverseitig gesnappte Geometrie nutzt
- oberhalb der Karte zeigt eine Verarbeitungsanzeige, ob alle aktuell verfügbaren Serverdaten verarbeitet sind oder noch Importpunkte fehlen

## Import-Verhalten

- ZIP-Archive werden vollständig entpackt
- unterstützt auch `.geo.json`
- der sichtbare Upload-Hinweis nennt `.geo.json` jetzt explizit mit
- Duplikate werden über `Zeitstempel + Latitude + Longitude` übersprungen
- erfolgreiche Importe erscheinen als eigene Import-Session
- Mobile Safari/iPhone nutzt einen gehärteten Datei-Picker ohne versteckten `display:none`-Input
- unter dem Fortschrittsbalken zeigt die Importseite eine Server-Statuskarte mit:
  - Importphase
  - Dateiname, Größe und erkanntem Format
  - Rohpunkten, neu importierten Punkten und übersprungenen Punkten
  - Dedupe in Datei und bereits vorhandenen Punkten
  - ZIP-Metadaten und Warnungen
  - Laufzeiten für Parsing, Insert und Gesamtverarbeitung
- serverseitige Warnungen und Fehlertexte werden nur noch escaped gerendert
- nach dem Löschen der letzten Import-Datei erscheint wieder der leere Zustand statt einer leeren Tabelle
