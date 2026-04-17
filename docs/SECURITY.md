# Security

## Secrets

- Bearer-Token nie in Git committen
- Secrets nie im Dashboard oder in JSON-Responses im Klartext rendern
- lokale `.env` bleibt unversioniert

## Ingest-Schutz

- optionaler Bearer-Token für `POST /live-location`
- optionales In-Memory-Rate-Limit
- Request-Body-Limit

## Dashboard-Schutz

- Session-Cookie nach Bearer-Login
- Cookie-Signatur über:
  - `SESSION_SIGNING_SECRET`, falls gesetzt
  - sonst `LIVE_LOCATION_BEARER_TOKEN`
  - sonst `ADMIN_PASSWORD`
  - sonst ein pro Prozess generierter Zufalls-Key
- optional HTTP Basic Auth mit `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- ohne Admin-Credentials lokal-only

## Netzwerk

- Backend nur auf `127.0.0.1:${PORT}`
- öffentlich nur Caddy auf `80/443`
- der TLS-Einstieg muss zum Zertifikats-Hostname passen

## Nicht-Ziele

- kein Multi-User-Rechtesystem
- keine externe Identity-Integration
- kein persistentes Rate-Limit-Backend
