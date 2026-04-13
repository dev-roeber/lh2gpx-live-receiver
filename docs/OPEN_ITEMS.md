# Open Items / Deferred Work

Diese Datei trennt bewusst zwischen dem jetzt abgeschlossenen Receiver-Kern und den Punkten, die absichtlich **nicht** Teil dieses Laufs waren.

## Jetzt real fertig

- stabile Annahme von `POST /live-location`
- robuste Persistenz über SQLite
- optionales NDJSON-Rohpayload-Audit
- Dashboard mit Kennzahlen, Punkteliste, Request- und Session-Details
- CSV-, JSON- und NDJSON-Exporte
- `health` und `readyz`
- strukturierte Logs mit `request_id`
- redigierte Secret-Darstellung in Logs, API und Dashboard
- Docker-/Compose-/Caddy-Deployment mit erfolgreichen lokalen und öffentlichen Smoke-Checks
- Merge nach `main`
- erfolgreiche Post-Merge-Verifikation auf `main`
- aus der Post-Merge-Verifikation keine weiteren Receiver-Änderungen nötig

## Für jetzt abgeschlossen

- der Receiver-Strang gilt für den aktuellen Scope als abgeschlossen
- weitere Arbeit an Receiver-Härtung Phase 2 bleibt bewusst getrennt
- App-/Wrapper-Abgleich bleibt bewusst getrennt
- ein echter End-to-End-iPhone-Gegenlauf gegen den finalen Receiver-Stand folgt später separat

## Bewusst verschoben, um Scope klein und stabil zu halten

- separate vollwertige Admin-Authentifizierung mit Session-Login
- weitergehende Zugriffshaertung für Dashboard/Admin jenseits des aktuellen Local-only-/Basic-Auth-Modells
- persistentes serverseitiges Rate-Limit-Backend
- automatische Daten-Retention
- geplante Export-Jobs oder Cron-basierte Exporte
- automatisierte Backup-/Restore-Orchestrierung
- formales Schema-Migrationsframework
- Karten-/Track-Preview in der Operator-UI

Begründung:

- dieser Lauf war bewusst auf einen stabilen Receiver-Kern begrenzt
- zuerst mussten Ingest, Speicherung, Listen, Exporte und Diagnose belastbar werden
- zusätzliche Härtungsschichten sollen später separat und kontrolliert folgen

## Empfohlene nächste Receiver-Schritte

- Admin-Zugriff mit eigenständiger Auth-Schicht und sauberer Rollen-/Zugriffsgrenze nachziehen
- Rotation und Austausch des derzeit lokal verwendeten Bearer-Test-Tokens vor weiterem externen Testbetrieb
- Retention-/Backup-Konzept für länger laufende Serverinstanzen festlegen
- kleines Wartungs-Runbook für SQLite-Vacuum, Exportzyklen und Restore-Proben konkretisieren
- optionales persistentes Rate-Limit oder Upstream-Schutz prüfen, falls der Dienst extern breiter erreichbar wird

## Spätere App-/Wrapper-Folgearbeiten

Diese Punkte wurden in diesem Lauf bewusst **nicht** umgesetzt:

- App-/Wrapper-Abgleich gegen den neuen Receiver-Stand
- appseitige Privacy-/Review-Anpassungen
- Bereinigung möglicher Testserver-/Testtoken-Defaults außerhalb dieses Repos; Testserver/Testwerte dürfen nicht Produktstandard bleiben
- finaler echter End-to-End-iPhone-Gegenlauf gegen den neuen Receiver

Begründung:

- dieser Lauf durfte nur den Receiver/Server anfassen
- App, Wrapper und lokale App-Daten blieben absichtlich unveraendert

## Security-/Operations-Folgearbeiten

- Admin-Zugriff haerter absichern, wenn Dashboard nicht nur lokal genutzt werden soll
- Token-Rotation nach extern sichtbar gewordenem Test-Token verbindlich einplanen und den alten Wert danach nirgends weiterverwenden
- Backup-/Restore-Probe mit dokumentierter Rueckspielzeit durchfuehren
- Alarmierung auf wiederholte `401`, `429`, `503` und unerwartete `500` ergaenzen

## Nicht Teil dieses Receiver-Laufs

- keine neuen Client-Funktionen
- keine Änderungen an App oder Wrapper
- keine Produkt-/Release-Annahmen für App-Defaults
- keine App-Store-Artefakte
- keine Migration oder Aenderung lokaler Standortdaten außerhalb dieses Repos
