# LH2GPX Receiver – Maintainer Guide

## Überblick

Diese Datei beschreibt den aktuellen technischen Wartungsstand des Repos. Sie ist absichtlich knapp und verweist für Details auf die spezialisierte Doku.

## Lokale Entwicklung

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python3 -m compileall app tests
./.venv/bin/pytest -q
./scripts/run-local.sh
```

## Aktuelle Architektur

- FastAPI-App in `app/main.py`
- SQLite-Storage in `app/storage.py`
- MapLibre-basierte Operator-Karte in `app/templates/map.html`
- serverseitig vorbereitete Karten-/Timeline-Pfade:
  - `/api/map-meta`
  - `/api/map-data`
  - `/api/timeline`
  - `/api/timeline-preview`
  - `/ws/map`
- lokaler Browser-Mirror via Dexie

## Wichtige aktuelle Storage-Bausteine

- `gps_points`
- `ingest_requests`
- `point_rollups`
- `timeline_day_markers`
- `gps_points_rtree`
- tile-basierte Raumspalten auf `gps_points`:
  - `tile_z10_x/y`
  - `tile_z14_x/y`

## Karten-/Timeline-Hot-Path

- Viewport-Abfragen laufen primär über `/api/map-data`
- globale Bounds/Metadaten über `/api/map-meta`
- Timeline-Daten über `/api/timeline`
- Timeline-Scrubbing/Replay über `/api/timeline-preview`
- Live-Hinweise über `/ws/map`
- der Kartenpfad nutzt:
  - RTree
  - tile-basierten Prefilter
  - In-Memory-Caches mit TTL und Größenlimit
  - Delta-/Noop-Refresh

## Tests

```bash
cd /home/sebastian/repos/lh2gpx-live-receiver
python3 -m compileall app tests
./.venv/bin/pytest -q
```

Der aktuelle Teststand liegt über den historischen 15 Tests und deckt u. a. Karte, Timeline, Delta-Pfade und Importstatus mit ab.

## Docker / Betrieb

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=200
curl http://127.0.0.1:8080/readyz
```

Öffentlicher TLS-Einstieg läuft über Caddy.

## Wahrheitsquellen

- API: `docs/API.md`
- Architektur: `docs/ARCHITECTURE.md`
- Datenmodell: `docs/DATA_MODEL.md`
- Betrieb: `docs/OPERATIONS.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`
- Website-Bedienung: `docs/WEBSEITE_BEDIENUNG.md`
- Website-Technik: `docs/WEBSEITE_TECHNISCH.md`

## Noch offene größere Maintainer-Themen

- feinere Teil-Deltas für weitere Kontextlayer
- noch stärkere ingest-nahe Voraggregation
- weitere Spatial-Modernisierung über `SQLite + RTree + Tile-Prefilter` hinaus
- weitere Modularisierung von `map.html`
