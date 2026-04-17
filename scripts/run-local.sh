#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export BIND_HOST="${BIND_HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
export SESSION_SIGNING_SECRET="${SESSION_SIGNING_SECRET:-}"
export SQLITE_PATH="${SQLITE_PATH:-${DATA_DIR}/receiver.sqlite3}"
export RAW_PAYLOAD_NDJSON_PATH="${RAW_PAYLOAD_NDJSON_PATH:-${DATA_DIR}/raw-payloads.ndjson}"
export LEGACY_REQUEST_NDJSON_PATH="${LEGACY_REQUEST_NDJSON_PATH:-${DATA_DIR}/live-location.ndjson}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export LOCAL_TIMEZONE="${LOCAL_TIMEZONE:-UTC}"
export REQUEST_BODY_MAX_BYTES="${REQUEST_BODY_MAX_BYTES:-262144}"
export POINTS_PAGE_SIZE_DEFAULT="${POINTS_PAGE_SIZE_DEFAULT:-50}"
export POINTS_PAGE_SIZE_MAX="${POINTS_PAGE_SIZE_MAX:-2000}"
export RATE_LIMIT_REQUESTS_PER_MINUTE="${RATE_LIMIT_REQUESTS_PER_MINUTE:-0}"
export TRUST_PROXY_HEADERS="${TRUST_PROXY_HEADERS:-true}"

exec python3 -m uvicorn app.main:app --host "${BIND_HOST}" --port "${PORT}" --log-level "${LOG_LEVEL,,}"
