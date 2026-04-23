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
- die Kartensteuerung sitzt als eigenes Dropdown `☰ Karte` oberhalb des Layer-Menüs
- `Auto-Center` behält den aktuellen Nutzer-Zoom bei
- normale `Linien` folgen Straßen deutlich näher, weil der Polyline-Layer bevorzugt serverseitig gesnappte Geometrie nutzt

## Import-Verhalten

- ZIP-Archive werden vollständig entpackt
- unterstützt auch `.geo.json`
- Duplikate werden über `Zeitstempel + Latitude + Longitude` übersprungen
- erfolgreiche Importe erscheinen als eigene Import-Session
- Mobile Safari/iPhone nutzt einen gehärteten Datei-Picker ohne versteckten `display:none`-Input
