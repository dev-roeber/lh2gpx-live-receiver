# Security

## Secrets

- Bearer-Token nur in lokaler, nicht versionierter Runtime-Konfiguration
- nie in Git committen
- nie in API-Responses rendern
- nie im Dashboard im Klartext rendern
- nie bewusst in Logs ausgeben

## Ingest-Schutz

- optionaler Bearer-Token fuer `POST /live-location`
- optionales Rate-Limit pro Minute
- Request-Body-Limit

## Operator-UI

- ohne Admin-Credentials lokal-only
- mit `ADMIN_USERNAME` und `ADMIN_PASSWORD` per Basic Auth geschuetzt

## Netzwerk

- Backend nur auf `127.0.0.1:${PORT}`
- oeffentlich nur Caddy auf `80/443`
- Security-Header werden am Proxy gesetzt

## Nicht-Ziele

- kein Multi-User-Rechtesystem
- keine externe Identity-Integration
- keine Third-Party-Analytics

## Token-Rotation

1. neuen Token ausserhalb von Git erzeugen
2. lokale `.env` anpassen
3. Receiver neu starten
4. alte Tokens in Clients manuell ersetzen

## Testdaten

Screenshot-Testwerte sind nur lokal und testweise zu verwenden. Sie gehoeren nicht in die versionierte Receiver-Konfiguration.
