#!/usr/bin/env sh
set -eu

APP_DIR="/app"
APP_USER="${APP_USER:-appuser}"
DATA_DIR="${DATA_DIR:-/app/data}"
LOGS_DIR="${LOGS_DIR:-/app/logs}"

mkdir -p "${DATA_DIR}" "${LOGS_DIR}"
if [ "$(id -u)" -eq 0 ]; then
  chown -R "${APP_USER}:${APP_USER}" "${DATA_DIR}" "${LOGS_DIR}"
  exec su -s /bin/sh "${APP_USER}" -c "${APP_DIR}/scripts/run-local.sh"
fi

exec "${APP_DIR}/scripts/run-local.sh"
