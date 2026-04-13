# AUDIT Receiver State (lh2gpx-live-receiver) - 2026-03-31_08-48

## 1. Ziel / Scope

Repo-wahre Statusdokumentation fuer den optionalen Self-Hosted-Receiver innerhalb des 4-Repo-Systems.

## 2. Gelesene Pflichtdateien

README.md, CHANGELOG.md, docs/API.md, docs/ARCHITECTURE.md, docs/DATA_MODEL.md, docs/OPERATIONS.md, docs/SECURITY.md, docs/OPEN_ITEMS.md, docs/AUDIT_4REPO_RECEIVER_2026-03-31_08-16.md

## 3. Frisch in diesem Lauf verifiziert

- `.venv/bin/python -m pytest tests/ -q --tb=short` -> 14 Tests, 0 Failures
- `docker compose config` -> valide
- `git status --short --branch` vor Änderungen sauber

## 4. Sicher belegter Ist-Stand

- Ingest-Endpoint vorhanden
- `health` und `readyz` vorhanden
- Dashboard, Punkteliste, Request-/Session-Details vorhanden
- CSV/JSON/NDJSON-Exporte vorhanden
- SQLite-/Hybrid-Storage vorhanden
- strukturierte Logs vorhanden

## 5. Historisch belegt, in diesem Lauf nicht frisch wiederholt

- laufender Server-Stack `Up (healthy)`
- erfolgreiche Live-Smokes gegen den laufenden Dienst
- beobachtete erfolgreiche Uploads im Receiver-Betrieb

Diese Punkte stammen aus dem frueheren 4-Repo-Abgleich am 2026-03-31_08-16 und wurden in diesem 08-48-Lauf nicht erneut gezogen.

## 6. Rolle im Gesamtsystem

- optionaler Self-Hosted-Server fuer Live-Punkte
- keine Pflicht fuer lokalen Import, lokale Analyse oder lokale Exporte
- kein zentraler Pflicht-Dienst

## 7. Offene Punkte

- Bearer-Token rotieren
- Admin-Auth / Operations-Härtung weiterfuehren
- App-seitige Testserver-/Testtoken-Defaults bereinigen; sie dürfen nicht als Produktstandard bestehen bleiben
- finalen End-to-End-iPhone-Gegenlauf später getrennt durchfuehren

## 8. Konkrete Doku-Korrekturen dieses Laufs

1. README trennt die Receiver-Rolle jetzt klarer von einer moeglichen Pflicht-Cloud
2. `docs/OPEN_ITEMS.md` fuehrt Token-Rotation und appseitige Testserver-Defaults expliziter

## 9. Ehrliche Grenzen

- kein neuer Live-Smoke gegen den laufenden Receiver in diesem 08-48-Lauf
- kein neuer externer Betriebsnachweis über Tests und Compose-Konfiguration hinaus

## 10. Abschlussfazit

Der Receiver bleibt der am staerksten als Serverbaustein ausgearbeitete Teil des Systems. Frisch bestaetigt sind in diesem Lauf Repo-Tests und Compose-Konfiguration; die tiefere Betriebsverifikation bleibt als frueherer, klar markierter Befund erhalten.
