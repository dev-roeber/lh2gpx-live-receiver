#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT:-8080}}"
TOKEN="${LIVE_LOCATION_BEARER_TOKEN:-}"

payload='{
  "source": "LocationHistory2GPX-iOS",
  "sessionID": "123e4567-e89b-12d3-a456-426614174000",
  "captureMode": "foregroundWhileInUse",
  "sentAt": "2026-03-20T12:00:00Z",
  "points": [
    {
      "latitude": 52.52,
      "longitude": 13.405,
      "timestamp": "2026-03-20T11:59:59Z",
      "horizontalAccuracyM": 6.5
    }
  ]
}'

health_code="$(curl -sS -o /tmp/lh2gpx-health.json -w '%{http_code}' "${BASE_URL}/health")"
test "${health_code}" = "200"

if [[ -n "${TOKEN}" ]]; then
  unauth_code="$(curl -sS -o /tmp/lh2gpx-live-unauth.json -w '%{http_code}' \
    -X POST "${BASE_URL}/live-location" \
    -H 'Content-Type: application/json' \
    -d "${payload}")"
  test "${unauth_code}" = "401"

  auth_code="$(curl -sS -o /tmp/lh2gpx-live-auth.json -w '%{http_code}' \
    -X POST "${BASE_URL}/live-location" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "${payload}")"
  test "${auth_code}" = "202"
else
  auth_code="$(curl -sS -o /tmp/lh2gpx-live-auth.json -w '%{http_code}' \
    -X POST "${BASE_URL}/live-location" \
    -H 'Content-Type: application/json' \
    -d "${payload}")"
  test "${auth_code}" = "202"
fi

echo "health_code=${health_code}"
echo "live_location_code=${auth_code}"
echo "health_body=$(cat /tmp/lh2gpx-health.json)"
echo "live_location_body=$(cat /tmp/lh2gpx-live-auth.json)"
