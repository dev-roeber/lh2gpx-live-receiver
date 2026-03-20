#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export BIND_HOST="${BIND_HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

exec python3 -m uvicorn app.main:app --host "${BIND_HOST}" --port "${PORT}" --log-level "${LOG_LEVEL,,}"

