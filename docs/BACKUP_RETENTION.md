# LH2GPX-Backup und Retention

## Status

Der Baustein ist im Repository vorhanden. Die User-Units sind seit dem
2026-09-06 installiert; `lh2gpx-backup.timer` ist aktiviert und läuft. Der
zugehörige Service wird alle sechs Stunden mit zufälliger Verzögerung gestartet.
Es wurde kein automatisches Löschen eingerichtet.

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

## Systemd-Units

`systemd/user/lh2gpx-backup.service` und `.timer` werden als User-Units unter
`~/.config/systemd/user/` installiert. Der Service setzt einen expliziten PATH,
weil `sqlite3` und `flock` auf diesem Server unter
`/home/linuxbrew/.linuxbrew/bin/` liegen. Das Zielverzeichnis wird mit Modus
`0700` betrieben; Archive und Prüfsummen werden durch `umask 077` privat
angelegt.

Der Timer ist mit `Persistent=true`, `RandomizedDelaySec=15min` und dem
Zeitplan `00/6:15:00` konfiguriert. Bei der Aktivierung wurde zuerst geprüft,
dass Quelle, Ziel, Berechtigungen und freier Speicher geeignet sind.

## Verifizierter Testlauf

Am 2026-09-06 wurde ein echter, nicht-destruktiver Lauf über
`systemctl --user start --wait lh2gpx-backup.service` ausgeführt. Der Receiver
blieb dabei aktiv; die SQLite-Datei wurde online mit `.backup` gesichert.

- Quelle: `/home/sebastian/services/lh2gpx-live-receiver/data/receiver.sqlite3`
- Ziel: `/home/sebastian/ki-backups/lh2gpx-live-receiver/`
- Ergebnis: `lh2gpx-20260906T044245Z.tar.gz`, 145340868 Bytes
- Inhalt: SQLite-Snapshot, vorhandenes `raw-payloads.ndjson`, Manifest
- `PRAGMA quick_check`: `ok`
- SHA-256-Prüfsumme: erfolgreich geprüft
- Retention: `automatic_deletion=false`; es wurde nichts gelöscht
- Beim Test waren rund 94 GB auf dem Ziel-Dateisystem frei

Das Ziel ist lokal und nicht als verschlüsseltes Offsite-Backup ausgelegt. Die
in „Noch nicht enthalten“ genannten Offsite-, Restore- und Dawarich-Themen
bleiben daher weiterhin offen.

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
