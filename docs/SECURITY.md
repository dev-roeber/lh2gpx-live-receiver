# Security

## Secrets

- Bearer-Token nur in lokaler, nicht versionierter Runtime-Konfiguration
- nie in Git committen
- nie in API-Responses rendern
- nie im Dashboard im Klartext rendern
- nie bewusst in Logs ausgeben

## Ingest-Schutz

- optionaler Bearer-Token für `POST /live-location`
- optionales Rate-Limit pro Minute
- Request-Body-Limit

## Operator-UI

- ohne Admin-Credentials lokal-only
- mit `ADMIN_USERNAME` und `ADMIN_PASSWORD` per Basic Auth geschützt

## Netzwerk

- Backend nur auf `127.0.0.1:${PORT}`
- öffentlich nur Caddy auf `80/443`
- Security-Header werden am Proxy gesetzt

## Nicht-Ziele

- kein Multi-User-Rechtesystem
- keine externe Identity-Integration
- keine Third-Party-Analytics

## Token-Rotation

1. neuen Token außerhalb von Git erzeugen
2. lokale `.env` anpassen
3. Receiver neu starten
4. alte Tokens in Clients manuell ersetzen

## Testdaten

Screenshot-Testwerte sind nur lokal und testweise zu verwenden. Sie gehören nicht in die versionierte Receiver-Konfiguration.

## Raw Payload NDJSON

Die Datei `raw-payloads.ndjson` (Standard: `/app/data/raw-payloads.ndjson`) speichert vollständige GPS-Payloads pro Ingest-Request im NDJSON-Format — inkl. Koordinaten, Zeitstempel und Request-ID.

- die Datei wird bei Ersterstellung mit Modus `0600` angelegt (nur Owner kann lesen/schreiben)
- bestehende Dateien werden nicht automatisch in ihrer Berechtigung geändert
- der Log kann über `ENABLE_RAW_PAYLOAD_NDJSON=false` deaktiviert werden
- Empfehlung: Datei regelmäßig rotieren oder löschen, wenn kein aktives Debugging erforderlich ist; für länger laufende Server-Instanzen ein Retention-Konzept festlegen

## Bewusst verschobene Security-Folgearbeiten

Aktuell **nicht** Teil dieses Laufs:

- separate vollwertige Admin-Authentifizierung mit Session-Login
- weitergehende Dashboard-Zugriffshaertung für nicht-lokale Operator-Nutzung
- persistentes serverseitiges Rate-Limit-Backend
- formale Token-Rotation außerhalb der lokalen Runtime-Konfiguration

Begründung:

- der Scope wurde bewusst klein gehalten, um zuerst den stabilen Ingest-, Storage- und Diagnosepfad fertigzustellen
- diese Punkte bleiben offen und sollten vor breiterem produktivem Einsatz separat umgesetzt werden

Siehe auch: [OPEN_ITEMS.md](OPEN_ITEMS.md)
