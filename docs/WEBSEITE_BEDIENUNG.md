# Webseite – Bedienung

## Einstieg

- `/login` für Bearer-basierten Dashboard-Login
- `/dashboard` leitet auf die Kartenansicht weiter

## Hauptbereiche

- `Übersicht`: Receiver-Zustand und Kennzahlen
- `Karte`: Live-Karte mit Polling, Zeitraum und Session-Filter
- `Punkte`: punktgenaue Detailansicht
- `Requests`: Upload-Historie
- `Sessions`: Session-Übersicht und Löschpfad
- `Import`: Dateiimport mit Task-Status
- `Storage`, `Config`, `Security`, `System`: Betriebs- und Diagnoseansicht

## Import-Verhalten

- ZIP-Archive werden vollständig entpackt
- Duplikate werden über `Zeitstempel + Latitude + Longitude` übersprungen
- erfolgreiche Importe erscheinen als eigene Import-Session
