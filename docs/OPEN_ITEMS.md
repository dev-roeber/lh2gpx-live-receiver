# Open Items / Deferred Work

Diese Datei trennt bewusst zwischen dem jetzt abgeschlossenen Receiver-Kern und den Punkten, die absichtlich **nicht** Teil dieses Laufs waren.

## Jetzt real fertig

- stabile Annahme von `POST /live-location`
- robuste Persistenz ueber SQLite
- optionales NDJSON-Rohpayload-Audit
- Dashboard mit Kennzahlen, Punkteliste, Request- und Session-Details
- CSV-, JSON- und NDJSON-Exporte
- `health` und `readyz`
- strukturierte Logs mit `request_id`
- redigierte Secret-Darstellung in Logs, API und Dashboard
- Docker-/Compose-/Caddy-Deployment mit erfolgreichen lokalen und oeffentlichen Smoke-Checks

## Bewusst verschoben, um Scope klein und stabil zu halten

- separate vollwertige Admin-Authentifizierung mit Session-Login
- weitergehende Zugriffshaertung fuer Dashboard/Admin jenseits des aktuellen Local-only-/Basic-Auth-Modells
- persistentes serverseitiges Rate-Limit-Backend
- automatische Daten-Retention
- geplante Export-Jobs oder Cron-basierte Exporte
- automatisierte Backup-/Restore-Orchestrierung
- formales Schema-Migrationsframework
- Karten-/Track-Preview in der Operator-UI

Begruendung:

- dieser Lauf war bewusst auf einen stabilen Receiver-Kern begrenzt
- zuerst mussten Ingest, Speicherung, Listen, Exporte und Diagnose belastbar werden
- zusaetzliche Härtungsschichten sollen spaeter separat und kontrolliert folgen

## Empfohlene naechste Receiver-Schritte

- Admin-Zugriff mit eigenstaendiger Auth-Schicht und sauberer Rollen-/Zugriffsgrenze nachziehen
- Rotation und Austausch des derzeit lokal verwendeten Test-Tokens vor weiterem externen Testbetrieb
- Retention-/Backup-Konzept fuer laenger laufende Serverinstanzen festlegen
- kleines Wartungs-Runbook fuer SQLite-Vacuum, Exportzyklen und Restore-Proben konkretisieren
- optionales persistentes Rate-Limit oder Upstream-Schutz pruefen, falls der Dienst extern breiter erreichbar wird

## Spaetere App-/Wrapper-Folgearbeiten

Diese Punkte wurden in diesem Lauf bewusst **nicht** umgesetzt:

- App-/Wrapper-Abgleich gegen den neuen Receiver-Stand
- appseitige Privacy-/Review-Anpassungen
- Bereinigung moeglicher Testserver-/Testtoken-Defaults ausserhalb dieses Repos
- finaler echter End-to-End-iPhone-Gegenlauf gegen den neuen Receiver

Begruendung:

- dieser Lauf durfte nur den Receiver/Server anfassen
- App, Wrapper und lokale App-Daten blieben absichtlich unveraendert

## Security-/Operations-Folgearbeiten

- Admin-Zugriff haerter absichern, wenn Dashboard nicht nur lokal genutzt werden soll
- Token-Rotation nach extern sichtbar gewordenem Test-Token verbindlich einplanen
- Backup-/Restore-Probe mit dokumentierter Rueckspielzeit durchfuehren
- Alarmierung auf wiederholte `401`, `429`, `503` und unerwartete `500` ergaenzen

## Nicht Teil dieses Receiver-Laufs

- keine neuen Client-Funktionen
- keine Aenderungen an App oder Wrapper
- keine Produkt-/Release-Annahmen fuer App-Defaults
- keine App-Store-Artefakte
- keine Migration oder Aenderung lokaler Standortdaten ausserhalb dieses Repos
