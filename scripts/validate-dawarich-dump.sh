#!/usr/bin/env bash
# Validate a local PostgreSQL custom-format dump without connecting anywhere.
set -Eeuo pipefail
umask 077

usage() {
  printf '%s\n' 'Verwendung: validate-dawarich-dump.sh DUMPFILE [CHECKSUMFILE]'
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
[[ $# -ge 1 && $# -le 2 ]] || { usage >&2; exit 2; }
DUMP="$(realpath -e -- "$1")" || { printf '%s\n' 'FEHLER: Dump fehlt' >&2; exit 1; }
[[ -f "$DUMP" ]] || { printf '%s\n' 'FEHLER: Dump ist keine reguläre Datei' >&2; exit 1; }
CHECKSUM="${2:-$DUMP.sha256}"
CHECKSUM="$(realpath -e -- "$CHECKSUM")" || { printf '%s\n' 'FEHLER: SHA-256-Datei fehlt' >&2; exit 1; }
[[ -f "$CHECKSUM" ]] || { printf '%s\n' 'FEHLER: SHA-256-Datei ist keine reguläre Datei' >&2; exit 1; }

read -r expected filename extra < "$CHECKSUM"
[[ -z "${extra:-}" && "$filename" == "$(basename "$DUMP")" ]] \
  || { printf '%s\n' 'FEHLER: SHA-256-Datei gehört nicht zum Dump' >&2; exit 1; }
[[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] \
  || { printf '%s\n' 'FEHLER: ungültiger SHA-256-Wert' >&2; exit 1; }
actual="$(sha256sum "$DUMP" | awk '{print $1}')"
[[ "$actual" == "${expected,,}" ]] \
  || { printf '%s\n' 'FEHLER: SHA-256-Prüfung fehlgeschlagen' >&2; exit 1; }

command -v pg_restore >/dev/null || { printf '%s\n' 'FEHLER: pg_restore fehlt' >&2; exit 1; }
# --list reads the archive catalog only; it does not connect to PostgreSQL.
pg_restore --list "$DUMP" >/dev/null
printf 'OK: PostgreSQL-Dump ist lesbar, SHA-256 stimmt, kein Netzwerkzugriff.\n'
