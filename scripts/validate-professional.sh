#!/bin/bash
set -e

BASE_URL="http://127.0.0.1:8080"
# Token aus der .env extrahieren (falls vorhanden)
TOKEN=$(grep LIVE_LOCATION_BEARER_TOKEN ~/live_receiver/.env | cut -d= -f2)

echo "--- 🛰️ Validierung: LH2GPX Professional Receiver ---"

# 1. Readyz Check
echo -n "[1/5] System Readiness Check... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/readyz")
if [ "$STATUS" -eq 200 ]; then echo "✅ OK"; else echo "❌ FAILED ($STATUS)"; exit 1; fi

# 2. Ingest Test (Valide)
echo -n "[2/5] Data Ingest Test (mit Token)... "
PAYLOAD='{"source":"ValidationScript","sessionID":"550e8400-e29b-41d4-a716-446655440000","captureMode":"high_accuracy","sentAt":"2026-04-13T10:00:00Z","points":[{"latitude":52.52,"longitude":13.40,"timestamp":"2026-04-13T10:00:00Z","horizontalAccuracyM":5.0}]}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/live-location" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "$PAYLOAD")
if [ "$STATUS" -eq 202 ]; then echo "✅ ACCEPTED"; else echo "❌ FAILED ($STATUS)"; exit 1; fi

# 3. Security Test (Invalide)
echo -n "[3/5] Security Check (ohne Token)... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/live-location" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")
if [ "$STATUS" -eq 401 ]; then echo "✅ REJECTED (Correct)"; else echo "❌ FAILED ($STATUS)"; exit 1; fi

# 4. Live Summary API Test
echo -n "[4/5] Live Summary API Check... "
RESPONSE=$(curl -s "$BASE_URL/api/live-summary")
if echo "$RESPONSE" | grep -q "recentPoints"; then echo "✅ OK"; else echo "❌ FAILED (Empty Response)"; exit 1; fi

# 5. Dashboard Accessibility
echo -n "[5/5] Dashboard Access Check... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dashboard")
if [ "$STATUS" -eq 200 ]; then echo "✅ OK"; else echo "❌ FAILED ($STATUS)"; exit 1; fi

echo "--- 🎉 Alle Tests erfolgreich bestanden! ---"
