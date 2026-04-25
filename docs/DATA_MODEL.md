# Data Model

## Primärer Storage

SQLite-Datei: `receiver.sqlite3`

## Tabellen

### `ingest_requests`

Speichert pro Request:

- `request_id`
- `received_at_utc`
- `sent_at_utc`
- `source`
- `session_id`
- `capture_mode`
- `points_count`
- `first_point_ts_utc`
- `last_point_ts_utc`
- `user_agent`
- `remote_addr`
- `proxied_ip`
- `ingest_status`
- `http_status`
- `error_category`
- `error_detail`
- `raw_payload_json`
- `raw_payload_reference`

### `gps_points`

Speichert pro Punkt:

- `id`
- `request_id`
- `received_at_utc`
- `sent_at_utc`
- `point_timestamp_utc`
- `latitude`
- `longitude`
- `horizontal_accuracy_m`
- `source`
- `session_id`
- `capture_mode`
- `point_date_local`
- `point_time_local`
- `point_timestamp_local`
- `tile_z10_x`
- `tile_z10_y`
- `tile_z14_x`
- `tile_z14_y`

Diese Tile-Spalten werden ingest-nah gefüllt und dienen als zusätzlicher räumlicher Prefilter für Kartenabfragen.

### `point_rollups`

Voraggregierte Zusammenfassungen für:

- `global`
- einzelne `session`

Gespeichert werden:

- `total_points`
- `first_point_ts_utc`
- `last_point_ts_utc`
- `min_latitude`
- `max_latitude`
- `min_longitude`
- `max_longitude`

Sie werden ingest-/import-nah aktualisiert und von `summarize_points()` als Fast-Path genutzt.

### `timeline_day_markers`

Voraggregierte Tagesmarker für die Timeline, jeweils:

- global
- pro Session

Gespeichert werden:

- `scope_type`
- `scope_key`
- `point_date_local`
- `first_point_ts_utc`
- `label`

Sie werden ingest-/import-nah aktualisiert und von `/api/timeline` als Fast-Path genutzt, wenn der Filter dafür geeignet ist.

### `gps_points_rtree`

SQLite-RTree für räumliche Punktabfragen:

- `id`
- `min_lon`
- `max_lon`
- `min_lat`
- `max_lat`

Der aktuelle Kartenpfad nutzt RTree plus tile-basierte Prefilter.

### `schema_metadata`

Kleine Metadaten-Tabelle, aktuell u. a. für:

- Legacy-NDJSON-Importstatus
- RTree-Backfill-Status
- Rollup-Backfill-Status
- Timeline-Day-Marker-Backfill-Status
- Tile-Spalten-Backfill-Status

## Optionales NDJSON

Wenn `ENABLE_RAW_PAYLOAD_NDJSON=true` gesetzt ist, schreibt der Receiver zusätzlich ein Rohpayload-Audit in `RAW_PAYLOAD_NDJSON_PATH`.

## Legacy-Import

Falls `LEGACY_REQUEST_NDJSON_PATH` existiert und die SQLite-DB noch leer ist, importiert der Receiver diese Datei einmalig als Bootstrap in die neue Datenbank.
