# LH2GPX-Backup und Retention

## Status

Dieser Baustein ist im Repository vorhanden, aber bewusst **nicht installiert,
nicht aktiviert und nicht deployed**. Es wurden keine Produktivdaten verändert.

Der sichere Default ist eine lokale Sicherung nach:

```text
~/ki-backups/lh2gpx-live-receiver/
```

Eine Storage-Box-Zielstruktur ist noch nicht festgelegt und wird von diesem
Baustein daher nicht verwendet.

## Inhalt

`backup-data.sh` erstellt einen konsistenten Snapshot von:

- `data/receiver.sqlite3`
- `data/raw-payloads.ndjson`, falls vorhanden
- `data/live-location.ndjson`, falls vorhanden
- einem nicht geheimen JSON-Manifest

Die produktiven Standardpfade sind:

```text
/home/sebastian/services/lh2gpx-live-receiver/data
/home/sebastian/services/lh2gpx-live-receiver/data/receiver.sqlite3
```

Der Snapshot wird mit SQLite `.backup` erstellt, danach mit `PRAGMA
quick_check` geprüft, als temporäres TAR.GZ erzeugt, per SHA-256 begleitet und
erst am Ende atomar in den Zielordner verschoben. Die laufende Receiver-Unit
muss dafür nicht gestoppt werden.

Secrets (`.env`, Dashboard-Sessions und Dateien unter `~/Secrets`) werden nicht
eingelesen und nicht in das Archiv aufgenommen.

## Retention

`retention-report.sh` ist absichtlich nur ein Bericht. Der Standard schützt die
14 neuesten Archive und listet ältere als Kandidaten auf. Es gibt in diesem
Baustein keinen Löschpfad und keine automatische Prune-Operation.

```bash
scripts/retention-report.sh \
  --root "$HOME/ki-backups/lh2gpx-live-receiver" \
  --keep 14
```

## Systemd-Vorlagen

`systemd/user/lh2gpx-backup.service` und `.timer` sind Vorlagen. Der Timer ist
für alle sechs Stunden mit zufälliger Verzögerung vorgesehen, aber nicht
installiert oder aktiviert. Vor einer Aktivierung müssen insbesondere ein
verschlüsseltes Offsite-Ziel, ein Restore-Test und eine Secret-/Schlüssel-
Strategie separat festgelegt werden.

## Noch nicht enthalten

- Dawarich-PostgreSQL-Dumps
- WAL-/Point-in-Time-Recovery
- Storage-Box-Upload
- verschlüsseltes Offsite-Repository
- automatisches Löschen
- automatisierter Restore-Test

Diese Punkte bleiben bewusst getrennt, weil dafür noch ein eindeutiger
Offsite-Zielpfad und eine gesonderte Schlüsselverwaltung festgelegt werden
müssen.
