#!/usr/bin/env bash
# Report retention candidates without deleting anything.
set -Eeuo pipefail
umask 077

ROOT="${LH2GPX_BACKUP_ROOT:-${HOME}/ki-backups/lh2gpx-live-receiver}"
KEEP="${LH2GPX_RETENTION_KEEP:-14}"

while (($#)); do
  case "$1" in
    --root)
      (($# >= 2)) || { printf '%s\n' 'FEHLER: --root benötigt einen Pfad' >&2; exit 2; }
      ROOT="$2"; shift 2
      ;;
    --keep)
      (($# >= 2)) || { printf '%s\n' 'FEHLER: --keep benötigt eine Zahl' >&2; exit 2; }
      KEEP="$2"; shift 2
      ;;
    --help)
      printf '%s\n' 'Verwendung: retention-report.sh [--root PFAD] [--keep ANZAHL]'
      exit 0
      ;;
    *)
      printf 'FEHLER: unbekannte Option: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { printf '%s\n' 'FEHLER: --keep muss positiv sein' >&2; exit 2; }
if [[ ! -d "$ROOT" ]]; then
  printf 'Retention-Report: Zielverzeichnis fehlt: %s\n' "$ROOT"
  exit 0
fi

mapfile -t archives < <(find "$ROOT" -maxdepth 1 -type f -name 'lh2gpx-*.tar.gz' -printf '%T@ %s %p\n' | sort -nr)
total=${#archives[@]}
printf 'Retention-Report: %d Archiv(e), geschützt bleiben die neuesten %s.\n' "$total" "$KEEP"

if (( total <= KEEP )); then
  printf '%s\n' 'Keine Retention-Kandidaten. Es wurde nichts gelöscht.'
  exit 0
fi

candidate_count=0
candidate_bytes=0
for ((i=KEEP; i<total; i++)); do
  record="${archives[$i]}"
  size="${record#* }"
  size="${size#* }"
  path="${record#* * }"
  candidate_count=$((candidate_count + 1))
  candidate_bytes=$((candidate_bytes + size))
  printf 'Kandidat (nicht gelöscht): %s\n' "$path"
done
printf 'Kandidaten: %d Archiv(e), %s Bytes. Es wurde nichts gelöscht.\n' "$candidate_count" "$candidate_bytes"
