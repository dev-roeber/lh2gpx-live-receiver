# Architecture

## Ziel

Der Receiver nimmt optionale Live-Location-Uploads an und macht sie fuer den Serverbetrieb sichtbar, exportierbar und diagnostizierbar.

## Bausteine

- FastAPI-App
- SQLite-Datenbank fuer Requests und GPS-Punkte
- optionales NDJSON fuer Rohpayload-Audit
- Caddy als TLS-Reverse-Proxy
- Operator-Dashboard in serverseitig gerendertem HTML

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
