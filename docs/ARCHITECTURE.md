# Architecture

## Ziel

Der Receiver nimmt optionale Live-Location-Uploads an und macht sie fuer den Serverbetrieb sichtbar, exportierbar und diagnostizierbar.

## Bausteine

- FastAPI-App
- SQLite-Datenbank fuer Requests und GPS-Punkte
- optionales NDJSON fuer Rohpayload-Audit
- Caddy als TLS-Reverse-Proxy
- receiver-first Operator-UI in serverseitig gerendertem HTML mit mehreren Admin-Views

## Request-Fluss

1. Client sendet `POST /live-location`
2. Middleware erzeugt `request_id`, misst Dauer und liest den Body kontrolliert ein
3. Bearer-Auth und optionales Rate-Limit greifen
4. Pydantic validiert den Input
5. Storage speichert:
   - Request-Metadaten
   - einzelne GPS-Punkte
   - optional Rohpayload-NDJSON
6. API antwortet mit `202 Accepted`
7. Logs enthalten strukturierte Diagnosedaten ohne Secret-Leaks

## Warum SQLite + NDJSON

- SQLite liefert schnelle Listen-, Filter- und Detailabfragen
- SQLite ist leicht zu sichern und benoetigt keine externe Datenbank
- NDJSON bleibt als leicht lesbarer Rohpayload-Auditpfad optional erhalten
- diese Kombination deckt Operator-UI und Export ohne unnötige Infrastruktur ab

## Fehlerbehandlung

- `401` fuer fehlende oder ungueltige Bearer-Tokens
- `413` fuer zu grosse Requests
- `422` fuer Payload-/Schemafehler
- `429` fuer Rate-Limit
- `503` fuer Storage-Probleme oder fehlende Schreibbereitschaft
- `500` nur fuer unerwartete Fehler

## Sicherheitsmodell

- Ingest getrennt von Operator-Zugriff
- Bearer-Token fuer Ingest optional
- Operator-UI lokal-only, bis Admin-Credentials gesetzt sind
- keine Secret-Anzeige in API oder HTML
- JSON-Access-Logs ueber Caddy

## Informationsarchitektur der Operator-UI

Die HTML-Oberflaeche ist entlang des Receiver-Betriebs gruppiert:

- Receiver: Dashboard, Live-Status, Letzte Aktivitaet
- Daten: Punkte, Requests, Sessions, Exporte
- Betrieb: Konfiguration, Storage, Troubleshooting, Open Items
- Sicherheit: Auth-Status und Security-Hinweise
- System: Version, Laufzeit und Changelog-Ausschnitte

Das erlaubt eine klarere Operator-Sicht, ohne die Ingest-, Storage- oder API-Logik umzubauen.

## Bewusst nicht umgesetzt

- kein eigenes Session-/Login-System fuer Operatoren
- kein kartenbasiertes Session-/Track-Preview
- kein externes Migrationsframework

Begruendung:

- der Lauf sollte den Receiver-Kern stabilisieren, nicht die zweite Ausbauphase vorwegnehmen
- offene Ausbaupunkte sind in [OPEN_ITEMS.md](OPEN_ITEMS.md) gesammelt
