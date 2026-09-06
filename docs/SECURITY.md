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

- zentrale Dashboard-Session aus `~/services/auth/sessions.db` über den Cookie `ytdl_session`
- die Session wird vom Dashboard erstellt und besitzt eine gleitende Gültigkeit
- der Receiver führt keine eigene Benutzer- oder Passwortanmeldung im Produktionsbetrieb durch

## Netzwerk

- Backend nur auf `127.0.0.1:${PORT}`
- im optionalen Compose-Modus öffentlich nur Caddy auf `80/443`; produktiv ist der Receiver lokal auf `127.0.0.1:8082` gebunden und nur über den zentralen Dashboard-Proxy erreichbar
- der TLS-Einstieg muss zum Zertifikats-Hostname passen

## Nicht-Ziele

- kein Multi-User-Rechtesystem
- keine externe Identity-Integration
- kein persistentes Rate-Limit-Backend
