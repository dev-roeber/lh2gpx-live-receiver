# Webseite – Bedienung

## Einstieg

- `/login` für Bearer-basierten Dashboard-Login
- `/dashboard` leitet auf die Kartenansicht weiter

## Hauptbereiche

- `Übersicht`: Receiver-Zustand und Kennzahlen
- `Karte`: MapLibre-Live-Karte mit serverseitig vorbereiteten Layern, Timeline, 3D, Kartensteuerungs-Dropdown, Zeitraum, Session-/Import-Filter und GeoJSON-Export
- `Punkte`: punktgenaue Detailansicht
- `Requests`: Upload-Historie
- `Sessions`: Session-Übersicht und Löschpfad
- `Import`: Dateiimport mit Task-Status
- `Live-Status`: Health-, Readiness- und Ingest-Zustand
- `Aktivität`: aktuelle Trends und Bewegungsdaten
- `Exports`: Exportwege und Formate
- `Storage`, `Config`, `Security`, `System`: Betriebs- und Diagnoseansicht
- `Troubleshooting`, `Open Items`: eingebettete Betriebsdoku

## Karte

- die Karte lädt globale Metadaten über `/api/map-meta` und Layer über `/api/map-data`
- die Karte arbeitet primär viewport-basiert; `Fallback-Punkte` greift nur ohne aktuellen Viewport
- Zeitfenster, Layer-Schalter, Session-/Import-Filter und Viewport wirken direkt auf das geladene Kartenmodell
- `Session Länge` und Kartenstatistik basieren auf den tatsächlich geladenen Track-Daten
- das Live-Log wird bei Filterwechseln sauber neu aufgebaut
- das Live-Log rendert ingestnahe Texte nur noch als Text und nicht als HTML
- die Kartensteuerung sitzt als eigenes Dropdown `☰ Karte` oberhalb des Layer-Menüs
- die Kartensteuerung enthält zusätzlich:
  - Browser-Standort
  - Schnellzugriff auf den neuesten Serverpunkt
  - 3D-Pitch
  - Vollbild
  - Legenden-Toggle
  - Fit-Bounds-Modus `Gesamt` oder `Ansicht`
- `Auto-Center` behält den aktuellen Nutzer-Zoom bei
- normale `Linien` folgen Straßen deutlich näher, weil der Polyline-Layer bevorzugt serverseitig gesnappte Geometrie nutzt
- ein Timeline-Regler kann die aktuell geladenen Punkte zeitlich filtern oder abspielen
- die Timeline bietet zusätzlich:
  - `Start`
  - `Zurück`
  - `Jetzt`
  - `Vor`
  - `Ende`
  - Quelle `Ansicht` oder `Filter`
  - Schrittmodus
  - Echtzeit-Replay
  - Auto-Follow
  - Aktivitätsleiste
  - Marker für Tageswechsel und Stops
- der Browser hält bereits geladene Punkte zusätzlich lokal in IndexedDB
- Live-Updates kommen hybrid über WebSocket-Hinweise, Delta-Refresh und konfigurierbares Polling
- während der Kartenabfrage zeigt ein Download-Overlay:
  - geladene Bytes
  - Prozent, wenn `Content-Length` vorhanden ist
  - Server-/Client-Phasen
  - ETA
  - Retry bei Fehlern
  - einen kompakten Sync-Hinweis bei schnellen Noop-/Delta-Fällen
- oberhalb der Karte zeigt eine Verarbeitungsanzeige, ob alle aktuell verfügbaren Serverdaten verarbeitet sind oder noch Importpunkte fehlen

## Weitere Seiten

- `Übersicht`: KPI-Kacheln, jüngste Requests, Sessions und Punkte
- `Live-Status`: Health, Readiness, letzter Ingest, Storage- und Fehlerstatus
- `Aktivität`: aktuelle Trends und Bewegungszusammenfassungen
- `Punkte`: filterbare Punktliste mit Exporten und Detailansicht
- `Requests`: Ingest-Historie mit Fehlerkategorien und Rohpayload-Detailansicht
- `Sessions`: Session-Liste mit Detailansicht und Löschpfad
- `Exports`: verfügbare Exportformate und Arbeitswege
- `Konfiguration`: speicherbare Laufzeit-Settings mit Live-Hot-Reload
- `Storage`: SQLite-/NDJSON-Status und `VACUUM`
- `Security`: Security-Doku und maskierte Config-Zusammenfassung
- `System`: App-Version, Python, Uptime und Changelog-Auszug
- `Troubleshooting` und `Open Items`: eingebettete Markdown-Dokumente

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
