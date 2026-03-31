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
ADMIN_USERNAME="${ADMIN_USERNAME:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
CHECK_ADMIN_UI="${CHECK_ADMIN_UI:-auto}"

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

readyz_code="$(curl -sS -o /tmp/lh2gpx-readyz.json -w '%{http_code}' "${BASE_URL}/readyz")"
test "${readyz_code}" = "200"

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

check_dashboard="false"
if [[ "${CHECK_ADMIN_UI}" = "true" ]]; then
  check_dashboard="true"
elif [[ "${CHECK_ADMIN_UI}" = "auto" && ( "${BASE_URL}" = http://127.0.0.1* || "${BASE_URL}" = http://localhost* || -n "${ADMIN_USERNAME}" ) ]]; then
  check_dashboard="true"
fi

dashboard_status="skipped"
points_code="skipped"
if [[ "${check_dashboard}" = "true" ]]; then
  dashboard_status="$(curl -sS -o /tmp/lh2gpx-dashboard.html -w '%{http_code}' "${BASE_URL}/dashboard")"
fi
if [[ -n "${ADMIN_USERNAME}" && -n "${ADMIN_PASSWORD}" && "${check_dashboard}" = "true" ]]; then
  auth_header="$(printf '%s:%s' "${ADMIN_USERNAME}" "${ADMIN_PASSWORD}" | base64 -w0)"
  dashboard_status="$(curl -sS -o /tmp/lh2gpx-dashboard.html -w '%{http_code}' \
    -H "Authorization: Basic ${auth_header}" \
    "${BASE_URL}/dashboard")"
fi
if [[ "${check_dashboard}" = "true" ]]; then
  test "${dashboard_status}" = "200"
fi

if [[ "${check_dashboard}" = "true" ]]; then
  points_code="$(curl -sS -o /tmp/lh2gpx-points.json -w '%{http_code}' \
    "${BASE_URL}/api/points")"
fi
if [[ -n "${ADMIN_USERNAME}" && -n "${ADMIN_PASSWORD}" && "${check_dashboard}" = "true" ]]; then
  auth_header="$(printf '%s:%s' "${ADMIN_USERNAME}" "${ADMIN_PASSWORD}" | base64 -w0)"
  points_code="$(curl -sS -o /tmp/lh2gpx-points.json -w '%{http_code}' \
    -H "Authorization: Basic ${auth_header}" \
    "${BASE_URL}/api/points")"
fi
if [[ "${check_dashboard}" = "true" ]]; then
  test "${points_code}" = "200"
fi

echo "health_code=${health_code}"
echo "readyz_code=${readyz_code}"
echo "live_location_code=${auth_code}"
echo "dashboard_code=${dashboard_status}"
echo "points_code=${points_code}"
echo "health_body=$(cat /tmp/lh2gpx-health.json)"
echo "readyz_body=$(cat /tmp/lh2gpx-readyz.json)"
echo "live_location_body=$(cat /tmp/lh2gpx-live-auth.json)"
if [[ "${check_dashboard}" = "true" ]]; then
  echo "points_body=$(cat /tmp/lh2gpx-points.json)"
fi
