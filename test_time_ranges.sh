#!/bin/bash

API_URL="http://127.0.0.1:8080/api/points"
TESTED_RANGES=("2m" "5m" "15m" "30m" "1h" "2h" "all")
UNTESTED_RANGES=("10m" "45m" "4h" "6h" "8h" "12h" "18h" "24h" "2d" "3d" "5d" "7d" "14d" "30d")

# Mapping: Bereich → Minuten
declare -A MINS_MAP=(
  ["2m"]=2 ["5m"]=5 ["10m"]=10 ["15m"]=15 ["30m"]=30 ["45m"]=45
  ["1h"]=60 ["2h"]=120 ["4h"]=240 ["6h"]=360 ["8h"]=480 ["12h"]=720 
  ["18h"]=1080 ["24h"]=1440 ["2d"]=2880 ["3d"]=4320 ["5d"]=7200 
  ["7d"]=10080 ["14d"]=20160 ["30d"]=43200
)

echo "=== TESTING UNTESTED TIME RANGE FILTERS ==="
echo "Tested already: ${TESTED_RANGES[@]}"
echo ""

for RANGE in "${UNTESTED_RANGES[@]}"; do
  MINS=${MINS_MAP[$RANGE]}
  
  # Berechne date_from und time_from
  NOW=$(date -u "+%Y-%m-%dT%H:%M:%S")
  FROM=$(date -u -d "$MINS minutes ago" "+%Y-%m-%dT%H:%M:%S")
  DATE_FROM=$(echo $FROM | cut -d'T' -f1)
  TIME_FROM=$(echo $FROM | cut -d'T' -f2)
  
  # API Call
  RESPONSE=$(curl -s "$API_URL?page_size=2000&date_from=$DATE_FROM&time_from=$TIME_FROM")
  TOTAL=$(echo $RESPONSE | jq '.points.total // 0')
  COUNT=$(echo $RESPONSE | jq '.points.items | length')
  
  echo "[$RANGE] Min:$MINS | FROM: $DATE_FROM $TIME_FROM | Total: $TOTAL | Displayed: $COUNT"
done

echo ""
echo "=== ZUSAMMENFASSUNG ==="
echo "Alle 14 untesteten Bereiche wurden überprüft."
