# Open Items / Deferred Work

Diese Datei beschreibt den **aktuellen** Restbestand nach dem inzwischen deutlich erweiterten Karten-, Timeline- und Backend-Ausbau.

## Bereits umgesetzt

- serverseitig vorbereitete Karten-Layer über `/api/map-data`
- globaler Karten-Metapfad `/api/map-meta`
- dedizierte Timeline-Endpunkte:
  - `/api/timeline`
  - `/api/timeline-preview`
- Hybrid-Live-Pfad:
  - WebSocket-Hinweise
  - Polling
  - Delta-/Noop-Refresh
- ingest-nahe Vorberechnung für:
  - `point_rollups`
  - `timeline_day_markers`
- räumliche Beschleunigung über:
  - `gps_points_rtree`
  - tile-basierte Prefilter

## Aktuell noch offen

- noch feinere echte Teil-Deltas für weitere Kontextlayer
  - besonders:
    - Stops
    - Daytracks
    - Snap

- noch stärkere ingest-nahe Vorberechnung
  - z. B. vorberechnete:
    - vereinfachte Tracks
    - Stop-Artefakte
    - Daytrack-Artefakte
    - Snap-Ergebnisse

- weitere Spatial-Modernisierung über `SQLite + RTree + Tile-Prefilter` hinaus
  - z. B.:
    - SpatiaLite
    - tile-/bucket-orientierte Voraggregation
    - später ggf. PostGIS

- weitere Modularisierung von `map.html`
  - Transport-/Delta-State
  - Timeline
  - Lade-/Progress-Logik
  - Renderer
  - UI/Controls

- Snap weiter aus dem heißen Live-/Renderpfad herausziehen

- Doku-/Audit-Nachzug künftig laufend aktuell halten

## Bewusst nicht Teil dieses Repos

- Änderungen an iOS-App oder Wrapper-Repos
- App-Store-Artefakte
- Produktvorgaben für App-Defaults außerhalb dieses Repos
