#!/usr/bin/env bash
# Create one consistent, local LH2GPX data snapshot.
# This script deliberately has no delete/prune operation.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
SOURCE_ROOT="${LH2GPX_SOURCE_ROOT:-/home/sebastian/services/lh2gpx-live-receiver}"
DATA_DIR="${LH2GPX_DATA_DIR:-$SOURCE_ROOT/data}"
SQLITE_PATH="${LH2GPX_SQLITE_PATH:-$DATA_DIR/receiver.sqlite3}"
BACKUP_ROOT="${LH2GPX_BACKUP_ROOT:-$HOME/ki-backups/lh2gpx-live-receiver}"

die() {
  printf 'FEHLER: %s\n' "$*" >&2
  exit 1
}

command -v sqlite3 >/dev/null || die "sqlite3 wurde nicht gefunden"
command -v tar >/dev/null || die "tar wurde nicht gefunden"
command -v sha256sum >/dev/null || die "sha256sum wurde nicht gefunden"
command -v flock >/dev/null || die "flock wurde nicht gefunden"
command -v python3 >/dev/null || die "python3 wurde nicht gefunden"

if ! DATA_DIR="$(realpath -e -- "$DATA_DIR")"; then
  die "Datenverzeichnis fehlt"
fi
if ! SQLITE_PATH="$(realpath -e -- "$SQLITE_PATH")"; then
  die "SQLite-Datei fehlt"
fi
case "$SQLITE_PATH" in
  "$DATA_DIR"/*) ;;
  *) die "SQLite-Datei liegt nicht im erwarteten Datenverzeichnis" ;;
esac

mkdir -p -- "$BACKUP_ROOT"
chmod 700 -- "$BACKUP_ROOT"
exec 9>"$BACKUP_ROOT/.backup.lock"
flock -n 9 || die "Ein anderer LH2GPX-Backup-Lauf ist bereits aktiv"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_DIR="$(mktemp -d "$BACKUP_ROOT/.staging.XXXXXX")"
ARCHIVE_TMP="$BACKUP_ROOT/.lh2gpx-$TIMESTAMP.tar.gz.tmp"
CHECKSUM_TMP="$BACKUP_ROOT/.lh2gpx-$TIMESTAMP.sha256.tmp"
ARCHIVE="$BACKUP_ROOT/lh2gpx-$TIMESTAMP.tar.gz"
CHECKSUM="$ARCHIVE.sha256"

[[ ! -e "$ARCHIVE" && ! -e "$CHECKSUM" ]] \
  || die "Zielarchiv existiert bereits; es wird nichts überschrieben"

cleanup() {
  rm -rf -- "$WORK_DIR"
  rm -f -- "$ARCHIVE_TMP" "$CHECKSUM_TMP"
}
trap cleanup EXIT

mkdir -p -- "$WORK_DIR/data"

# SQLite's online backup command creates a consistent snapshot while the
# receiver remains online and accounts for the database's WAL state.
sqlite3 "$SQLITE_PATH" ".backup '$WORK_DIR/data/receiver.sqlite3'"
[[ "$(sqlite3 "$WORK_DIR/data/receiver.sqlite3" 'PRAGMA quick_check;')" == "ok" ]] \
  || die "SQLite quick_check des Snapshots ist fehlgeschlagen"

# Optional legacy/raw files are copied only from the configured data directory.
for optional in raw-payloads.ndjson live-location.ndjson; do
  if [[ -f "$DATA_DIR/$optional" ]]; then
    cp -- "$DATA_DIR/$optional" "$WORK_DIR/data/$optional"
  fi
done

export TIMESTAMP DATA_DIR SQLITE_PATH WORK_DIR
python3 - "$WORK_DIR/manifest.json" <<'PY'
import json
import os
from pathlib import Path

work_dir = Path(os.environ["WORK_DIR"])
files = []
for path in sorted((work_dir / "data").iterdir()):
    if path.is_file():
        files.append({"path": str(path.relative_to(work_dir)), "bytes": path.stat().st_size})

manifest = {
    "format": "lh2gpx-local-snapshot-v1",
    "created_at_utc": os.environ["TIMESTAMP"],
    "source_data_dir": os.environ["DATA_DIR"],
    "source_sqlite_path": os.environ["SQLITE_PATH"],
    "sqlite_quick_check": "ok",
    "contains_application_secrets": False,
    "included_files": files,
    "retention": {
        "mode": "report-only",
        "automatic_deletion": False,
        "keep_newest_archives": int(os.getenv("LH2GPX_RETENTION_KEEP", "14")),
    },
}
(work_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY

tar -czf "$ARCHIVE_TMP" -C "$WORK_DIR" data manifest.json
mv -- "$ARCHIVE_TMP" "$ARCHIVE"
hash="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
printf '%s  %s\n' "$hash" "$(basename "$ARCHIVE")" >"$CHECKSUM_TMP"
mv -- "$CHECKSUM_TMP" "$CHECKSUM"

printf 'Backup erstellt: %s (%s)\n' "$ARCHIVE" "$(du -h "$ARCHIVE" | awk '{print $1}')"
"$SCRIPT_DIR/retention-report.sh" --root "$BACKUP_ROOT" --keep "${LH2GPX_RETENTION_KEEP:-14}"
