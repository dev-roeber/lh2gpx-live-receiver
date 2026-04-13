# Operations

## Regelbetrieb

- `docker compose ps`
- `docker compose logs --tail=200`
- `curl http://127.0.0.1:8080/readyz`
- `./scripts/smoke-test.sh`

## Aktueller Status

- der Receiver gilt für jetzt als abgeschlossen
- `main` wurde nach dem Merge noch einmal direkt im laufenden Setup geprueft
- aus dieser Post-Merge-Verifikation ergaben sich keine weiteren Sofortmassnahmen im Receiver-Repo
- ein parallel beobachteter erfolgreicher Upload-Betrieb passt zum aktuellen Receiver-Zustand, fuehrt hier aber nicht zu App-/Wrapper-Änderungen
- der 0600-Fix greift beim Anlegen neuer `raw-payloads.ndjson`-Dateien; vorhandene Altbestaende werden dadurch nicht automatisch umgestellt und müssen bei Bedarf operativ nachgeprueft werden

## Backups

Mindestens sichern:

- `DATA_DIR/receiver.sqlite3`
- optional `RAW_PAYLOAD_NDJSON_PATH`
- `compose.yaml`
- lokale `.env` außerhalb von Git

Hostseitig reicht für kleine Setups bereits ein reguläres Dateisystem-Backup des Repo-Verzeichnisses ohne `.venv`.

## Restore

1. Receiver stoppen
2. `receiver.sqlite3` und optionale NDJSON-Dateien wiederherstellen
3. `docker compose up -d`
4. `readyz`, Dashboard und Punktliste prüfen

## Wartung

- SQLite nutzt WAL-Mode
- bei größeren Datenmengen gelegentlich `VACUUM` im Wartungsfenster erwägen
- bei Speicherknappheit alte Exporte sichern und Daten-Retention bewusst planen

## Monitoring-Minimum

- `readyz`
- letzte Fehler im Dashboard
- JSON-Logs von Caddy und App
- Punkt- und Request-Anzahl über `/api/stats`
- `RAW_PAYLOAD_NDJSON_PATH` nur als optionales Betriebsartefakt behandeln; Rechteprobleme oder Altbestaende dort sind ein separater operativer Check, kein implizit reparierter Laufzeitzustand

## Operator-UI im Regelbetrieb

Die HTML-Views sind jetzt als Arbeitsbereiche gedacht:

- Dashboard für den schnellen Receiver-Befund
- Live-Status für Health, Readiness, Storage und Fehlerlage
- Letzte Aktivität für Trends, jüngste Requests, Sessions und Punkte
- Punkte / Requests / Sessions für die operative Detailarbeit
- Storage / Konfiguration / Sicherheit für Betriebs- und Härtungsfragen
- Troubleshooting / Open Items für bekannte Probleme und bewusst offene Folgearbeit

## Bewusst verschoben

Noch **nicht** Teil dieses Receiver-Laufs:

- geplante Export-Jobs
- automatische Retention
- automatisierte Backup-/Restore-Pipeline
- persistentes Rate-Limit-Backend
- Karten-/Track-Preview im Dashboard

Begründung:

- erst wurde der stabile Receiver-Kern mit Ingest, Speicherung, Listen, Exporten und Diagnose fertiggezogen
- weitergehende Betriebsautomatisierung folgt separat
- die Härtung bestehender Raw-Payload-Dateien ist kein automatischer Repo-Fix, sondern bei Altbestaenden ein Betriebs- bzw. Migrationsschritt

Siehe auch: [OPEN_ITEMS.md](OPEN_ITEMS.md)
