# Restore- und Offsite-Backup-Konzept

## Verifizierter Ist-Zustand

- LH2GPX läuft produktiv mit User-systemd und schreibt nach
  `/home/sebastian/services/lh2gpx-live-receiver/data/receiver.sqlite3`.
- Der lokale User-Timer `lh2gpx-backup.timer` ist aktiviert und erzeugt derzeit
  nicht-destruktive Archive unter
  `/home/sebastian/ki-backups/lh2gpx-live-receiver/`.
- Das vorhandene LH2GPX-Archiv besitzt ein SHA-256-Sidecar und wurde mit einem
  SQLite-`quick_check` erzeugt.
- Die lokale Sicherung ist weder verschlüsselt noch offsite. Der Validator lädt
  nichts hoch und kontaktiert keinen Dienst.
- Dawarich verwendet Podman-generierte User-Units. Die führende Datenbank liegt
  auf dem Host unter `/home/sebastian/services/dawarich/db` und wird im
  Container als PostgreSQL-Datenverzeichnis verwendet.
- Ein automatisierter Dawarich-PostgreSQL-Dump und ein verifiziertes Offsite-
  Backup wurden bei der Bestandsaufnahme nicht gefunden.

## Was geschützt werden muss

### LH2GPX

Pflichtbestandteile:

- `data/receiver.sqlite3`
- optional `data/raw-payloads.ndjson` und `data/live-location.ndjson`
- Sync-Zustand in der Receiver-SQLite, insbesondere der Dawarich-Cursor

Die SQLite-Spiegelung kann aus Dawarich neu aufgebaut werden, enthält aber auch
Receiver-eigene Requests und lokale Punkte. Sie darf deshalb nicht als bloß
entbehrlicher Cache behandelt werden.

### Dawarich

Pflichtbestandteile:

- PostgreSQL-Datenbank inklusive `receiver_sync_events`-Outbox
- PostgreSQL-Rollen-/Restore-Metadaten in einem separaten geschützten Dump
- Dawarich `storage`, `public` und `watched`, sofern dort importierte Dateien
  oder nutzerrelevante Anhänge liegen
- Versionen/Hashes der Containerdefinitionen und des verwendeten Images

Redis ist primär Cache- und Jobzustand; Photon und Tiles sind große,
wiederaufbaubare Bestände. Sie sollten zunächst inventarisiert, aber nicht in
jede Kernkopie aufgenommen werden.

## Offline-Validierung

LH2GPX-Archiv prüfen:

```bash
scripts/validate-lh2gpx-backup.py \
  "$HOME/ki-backups/lh2gpx-live-receiver/lh2gpx-<timestamp>.tar.gz"
```

Der Prüfer:

- verlangt die passende SHA-256-Datei
- akzeptiert nur die erwarteten Archivpfade
- lehnt absolute Pfade, `..`, Symlinks und unerwartete Dateien ab
- prüft Manifest-Dateiliste und Dateigrößen
- extrahiert ausschließlich in ein temporäres Verzeichnis
- prüft die SQLite-Kopie read-only mit `PRAGMA quick_check`
- prüft die erwarteten Receiver-/Sync-Tabellen

Ein Dawarich-Custom-Format-Dump kann ohne Datenbankverbindung geprüft werden:

```bash
scripts/validate-dawarich-dump.sh \
  /pfad/dawarich-<timestamp>.dump
```

Das Skript prüft die SHA-256-Datei und verwendet ausschließlich
`pg_restore --list`. Es führt weder `psql` noch `pg_restore` gegen einen
Server aus.

## Verifizierter Restore-Test

Der vorhandene LH2GPX-Stand kann zusätzlich in ein isoliertes temporäres Ziel
restore-getestet werden:

```bash
scripts/test-lh2gpx-restore.py \
  "$HOME/ki-backups/lh2gpx-live-receiver/lh2gpx-<timestamp>.tar.gz"
```

Der Test führt zuerst den vollständigen Offline-Validator aus und extrahiert
danach nur erlaubte reguläre Dateien unter einem automatisch verwalteten
System-Tempverzeichnis. Dort werden Manifest, SQLite-`quick_check`, erwartete
Kern-Tabellen, Punktzahlen und der Dawarich-Sync-Cursor read-only geprüft. Das
Produktivverzeichnis, die laufende SQLite-Datei, systemd und PostgreSQL werden
nicht als Restore-Ziel verwendet.

Der Test-Tempordner wird nach dem Prozessende automatisch entfernt; es werden
dabei keine Produktivdaten oder Backuparchive gelöscht.

Betriebsprüfung ohne Zustandsänderung:

```bash
systemctl --user is-active lh2gpx-live-receiver.service
systemctl --user is-active lh2gpx-dawarich-sync.service
stat "$HOME/services/lh2gpx-live-receiver/data/receiver.sqlite3"
```

Vor und nach dem Test müssen Dateigröße und Änderungszeit der Produktiv-
SQLite-Datei unverändert sein. Der Test selbst darf keine `systemctl`-,
`curl`-, `psql`-, Upload- oder Löschoperation ausführen.

## Sicherer Restore-Ablauf

1. Backupgeneration, SHA-256-Dateien und Manifest zunächst offline validieren.
2. Restore immer zuerst in ein temporäres Ziel bzw. eine temporäre Datenbank
   durchführen; niemals direkt über eine laufende Produktivdatei schreiben.
3. PostgreSQL und Receiver-Snapshot nur aus derselben Generation kombinieren.
4. Bei abweichendem Dawarich-/Receiver-Cursor den Receiver-Mirror nicht blind
   verwenden, sondern nach bestätigtem Backup einen vollständigen Sync-Neuaufbau
   durchführen.
5. Erst nach Integritäts-, Größen- und Stichprobenprüfung die Dienste in dieser
   Reihenfolge starten: PostgreSQL, Dawarich, Receiver, Dawarich-Sync.
6. `/health`, `/readyz`, Sync-Cursor, Punktzahlen und einige bekannte Zeit-/GPS-
   Stichproben prüfen.
7. Einen Restore-Test niemals als Schreibtest gegen die Produktionsdatenbank
   ausführen.

## Datenschutz und Schlüssel

Standortdaten, Rohpayloads, PostgreSQL-Dumps und Receiver-SQLite sind sensible
personenbezogene Daten. Deshalb gelten:

- keine `.env`-Dateien, Session-Daten oder Dateien unter `~/Secrets` in
  unverschlüsselten Archiven
- Dateirechte für lokale Backupverzeichnisse `0700`, Dateien `0600`
- Offsite-Kopie nur in einem verschlüsselten Repository
- separates Backup-Passwort bzw. Schlüsselmaterial, nicht aus App-Secrets
  ableiten
- Wiederherstellungsschlüssel zusätzlich offline aufbewahren
- Manifest und Logs dürfen keine Tokens, Passwörter oder Rohpayloads ausgeben

Eine SHA-256-Prüfsumme schützt die Übertragung gegen zufällige Beschädigung,
ersetzt aber weder Verschlüsselung noch einen getrennt aufbewahrten
Authentifizierungsschlüssel.

## Offsite-Plan, noch nicht aktiviert

Die Storage Box ist unter `/mnt/storagebox` erreichbar, aber ein dedizierter
Backup-Unterpfad ist noch nicht als verbindliches Ziel festgelegt. Vor jeder
Aktivierung müssen daher entschieden und dokumentiert werden:

- exakter Zielpfad
- verschlüsseltes Repository-Verfahren
- getrennte Schlüsselablage und Notfallzugriff
- RPO/RTO für Dawarich und Receiver
- Aufbewahrung und manueller Freigabeprozess für Löschungen

Bis dahin gibt es keinen Upload, kein automatisches Pruning und keine
automatische Löschung.
