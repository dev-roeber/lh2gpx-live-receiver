# Data Model

## Primaerer Storage

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

### `schema_metadata`

Kleine Metadaten-Tabelle, aktuell fuer den Legacy-NDJSON-Importstatus.

## Optionales NDJSON

Wenn `ENABLE_RAW_PAYLOAD_NDJSON=true` gesetzt ist, schreibt der Receiver zusaetzlich ein Rohpayload-Audit in `RAW_PAYLOAD_NDJSON_PATH`.

## Legacy-Import

Falls `LEGACY_REQUEST_NDJSON_PATH` existiert und die SQLite-DB noch leer ist, importiert der Receiver diese Datei einmalig als Bootstrap in die neue Datenbank.
